from __future__ import annotations

"""Utility functions for price prediction using embeddings.

The regression model tries to predict the logarithm of the price from the
embedding vectors.  Using log-scale makes the coefficients interpretable as
multiplicative factors.  Currencies are modelled as one-hot features relative to
a fixed USD base so the learnt coefficients can be interpreted as exchange
rates.
"""

import math
from typing import Iterable, Mapping
import json
from urllib.request import urlopen

import numpy as np
from sklearn.linear_model import LinearRegression

from log_utils import get_logger

# Map various currency spellings to ISO-4217 codes.
CURRENCY_ALIASES = {
    "usd": "USD",
    "eur": "EUR",
    "gel": "GEL",
    "lari": "GEL",
    "lar": "GEL",
    "uah": "UAH",
    "rub": "RUB",
    "tl": "TRY",
    "try": "TRY",
}


def canonical_currency(code: str | None) -> str | None:
    """Return canonical currency code or ``None`` when unknown."""
    if code is None:
        return None
    key = str(code).strip().lower()
    if not key:
        return None
    if key in {"currency units", "units", "unit"}:
        return None
    return CURRENCY_ALIASES.get(key, key.upper())


def fetch_official_rates() -> dict[str, float]:
    """Return currency multipliers relative to USD from NBG."""
    url = "https://nbg.gov.ge/gw/api/ct/monetarypolicy/currencies/en/json"
    try:
        with urlopen(url, timeout=10) as resp:
            data = json.load(resp)
    except Exception:
        log.exception("Failed to fetch NBG rates")
        return {}
    if not data or not isinstance(data, list) or not data[0].get("currencies"):
        log.error("Bad NBG response")
        return {}
    rates_gel = {"GEL": 1.0}
    usd = None
    for item in data[0]["currencies"]:
        try:
            code = item["code"].upper()
            rate = float(item["rate"]) / float(item.get("quantity", 1))
        except Exception:
            continue
        rates_gel[code] = rate
        if code == "USD":
            usd = rate
    if not usd:
        log.error("USD rate missing in NBG data")
        return {}
    rates: dict[str, float] = {"USD": 1.0, "GEL": usd}
    for code, val in rates_gel.items():
        if code in {"USD", "GEL"}:
            continue
        if val:
            rates[code] = usd / val
    log.info("Fetched official rates", rates=rates)
    return rates

log = get_logger().bind(module=__name__)


# ---------------------------------------------------------------------------
# Model training
# ---------------------------------------------------------------------------

def train_price_regression(
    lots: Iterable[Mapping],
    id_to_vec: Mapping[str, list[float]],
) -> tuple[LinearRegression | None, dict[str, int], dict[str, int]]:
    """Return ``(model, currency_map, counts)`` trained on ``lots``.

    ``lots`` must contain ``price`` and ``price:currency`` fields. Only lots with
    embeddings present in ``id_to_vec`` are considered. Prices are regressed on
    the logarithm scale so coefficients are interpretable as multiplicative
    factors. ``USD`` is treated as the base currency so coefficients can be
    interpreted as exchange rate multipliers. The returned ``counts`` dictionary
    maps each currency to the number of training samples observed.
    """

    # ``prepared`` accumulates validated samples as ``(vec, log_price, currency)``
    samples: list[list[float]] = []
    targets: list[float] = []
    # Keep track of currencies we encounter to build one-hot vectors.
    all_currencies = {"USD"}
    prepared: list[tuple[list[float], float, str]] = []
    counts: dict[str, int] = {}
    dim = None  # Embedding dimensionality for validation
    for lot in lots:
        price = lot.get("price")
        curr_raw = lot.get("price:currency")
        lid = lot.get("_id")
        curr = canonical_currency(curr_raw)
        if curr_raw is not None and curr != curr_raw:
            log.debug("Canonicalised currency", original=curr_raw, canonical=curr, id=lid)
        vec = id_to_vec.get(lid)
        if price is None or curr is None or vec is None:
            continue
        try:
            p = float(price)
        except Exception:
            continue
        if not math.isfinite(p) or p <= 0:
            continue
        if dim is None:
            # Store vector dimension to ensure all samples match
            dim = len(vec)
        elif len(vec) != dim:
            log.debug("Vector dim mismatch", id=lid)
            continue
        all_currencies.add(str(curr))
        counts[curr] = counts.get(curr, 0) + 1
        # Regression is done on the logarithm scale
        prepared.append((list(vec), math.log(p), str(curr)))

    if not prepared:
        log.info("No samples for price regression")
        return None, {}, {}

    # Map currency name to one-hot index, USD always goes first
    currencies = {
        cur: i
        for i, cur in enumerate(
            sorted(all_currencies, key=lambda c: 0 if c == "USD" else 1)
        )
    }
    for vec, log_price, curr in prepared:
        idx = currencies[curr]
        row = list(vec)
        if idx > 0:
            row.extend([1 if i == idx - 1 else 0 for i in range(len(currencies) - 1)])
        else:
            row.extend([0 for _ in range(len(currencies) - 1)])
        samples.append(row)
        targets.append(log_price)

    X = np.array(samples)
    y = np.array(targets)
    model = LinearRegression()
    model.fit(X, y)
    log.info(
        "Trained price model",
        samples=len(samples),
        currencies=len(currencies),
        counts=counts,
    )
    return model, currencies, counts


# ---------------------------------------------------------------------------
# Prediction helpers
# ---------------------------------------------------------------------------

def predict_price(
    model: LinearRegression | None,
    currencies: Mapping[str, int],
    vec: list[float] | None,
    currency: str | None,
) -> float | None:
    """Return predicted price for ``vec`` in ``currency``.

    When ``model`` is ``None`` or ``vec`` is missing, ``None`` is returned."""

    if model is None or vec is None:
        return None
    dim = len(vec)
    row = list(vec)
    idx = currencies.get(str(currency), 0)
    if idx > 0:
        row.extend([1 if i == idx - 1 else 0 for i in range(len(currencies) - 1)])
    else:
        row.extend([0 for _ in range(len(currencies) - 1)])
    pred = model.predict([row])[0]
    return float(math.exp(pred))


def currency_rates(model: LinearRegression, currencies: Mapping[str, int]) -> dict[str, float]:
    """Return estimated currency multipliers relative to the base.

    The regression model learns one coefficient per currency dummy feature.  The
    coefficient is the logarithm of the multiplier relative to USD.
    """

    dim = model.coef_.shape[0] - (len(currencies) - 1)
    rates: dict[str, float] = {}
    for curr, idx in currencies.items():
        if idx == 0:
            rates[curr] = 1.0
        else:
            coef = model.coef_[dim + idx - 1]
            rates[curr] = float(math.exp(coef))
    return rates


def guess_currency(
    rates: Mapping[str, float],
    price: float,
    pred_usd: float,
    counts: Mapping[str, int] | None = None,
    min_samples: int = 50,
) -> str | None:
    """Return currency with multiplier closest to ``price/pred_usd``.

    ``pred_usd`` is the predicted price in USD.  ``price`` is the numeric value
    provided by the user without a currency.  The function compares the implied
    multiplier ``price / pred_usd`` against the learnt exchange rates and picks
    the closest match.  ``counts`` may be provided to ignore rarely seen
    currencies when guessing.  Any currency with fewer than ``min_samples``
    samples in the training set is skipped.
    """

    if not rates or pred_usd <= 0 or not math.isfinite(pred_usd) or price <= 0:
        return None
    ratio = price / pred_usd
    best_cur = None
    best_diff = float("inf")
    for cur, mul in rates.items():
        if counts and counts.get(cur, 0) < min_samples:
            continue
        diff = abs(ratio - mul)
        if diff < best_diff:
            best_diff = diff
            best_cur = cur
    return best_cur


def _guess_currency_verified(
    ai_rates: Mapping[str, float],
    official_rates: Mapping[str, float],
    price: float,
    pred_usd: float,
    counts: Mapping[str, int] | None,
    min_samples: int = 50,
) -> str | None:
    """Return currency when both AI and official rates agree."""

    guess_ai = guess_currency(ai_rates, price, pred_usd, counts, min_samples)
    guess_of = guess_currency(official_rates, price, pred_usd, counts, min_samples)
    if guess_ai and guess_ai == guess_of:
        return guess_ai
    return None


def apply_price_model(
    lots: Iterable[Mapping],
    id_to_vec: Mapping[str, list[float]],
    official_rates: Mapping[str, float] | None = None,
) -> dict[str, float]:
    """Predict prices in USD and guess missing currencies."""
    log.debug("Training price model")
    price_model, currency_map, counts = train_price_regression(lots, id_to_vec)
    ai_rates = currency_rates(price_model, currency_map) if price_model else {}
    if ai_rates:
        log.info("Regressed currency rates", rates=ai_rates)
    if official_rates:
        log.info("Official currency rates", rates=official_rates)
    for lot in lots:
        vec = id_to_vec.get(lot["_id"])
        pred_usd = predict_price(price_model, currency_map, vec, "USD")
        if pred_usd is not None:
            lot["ai_price"] = round(pred_usd, 2)
        if lot.get("price") is not None and lot.get("price:currency") is None:
            try:
                price_val = float(lot["price"])
            except Exception:
                price_val = None
            if price_val and pred_usd:
                guessed = _guess_currency_verified(
                    ai_rates,
                    official_rates or {},
                    price_val,
                    pred_usd,
                    counts,
                )
                if guessed:
                    lot["price:currency"] = guessed
    return ai_rates



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

import numpy as np
from sklearn.linear_model import LinearRegression

from log_utils import get_logger

log = get_logger().bind(module=__name__)


# ---------------------------------------------------------------------------
# Model training
# ---------------------------------------------------------------------------

def train_price_regression(
    lots: Iterable[Mapping],
    id_to_vec: Mapping[str, list[float]],
) -> tuple[LinearRegression | None, dict[str, int]]:
    """Return ``(model, currency_map)`` trained on ``lots``.

    ``lots`` must contain ``price`` and ``price:currency`` fields. Only lots with
    embeddings present in ``id_to_vec`` are considered. Prices are regressed on
    the logarithm scale so coefficients are interpretable as multiplicative
    factors. ``USD`` is treated as the base currency so coefficients can be
    interpreted as exchange rate multipliers.
    """

    # ``prepared`` accumulates validated samples as ``(vec, log_price, currency)``
    samples: list[list[float]] = []
    targets: list[float] = []
    # Keep track of currencies we encounter to build one-hot vectors.
    all_currencies = {"USD"}
    prepared: list[tuple[list[float], float, str]] = []
    dim = None  # Embedding dimensionality for validation
    for lot in lots:
        price = lot.get("price")
        curr = lot.get("price:currency")
        lid = lot.get("_id")
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
        # Regression is done on the logarithm scale
        prepared.append((list(vec), math.log(p), str(curr)))

    if not prepared:
        log.info("No samples for price regression")
        return None, {}

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
    log.info("Trained price model", samples=len(samples), currencies=len(currencies))
    return model, currencies


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


def guess_currency(rates: Mapping[str, float], price: float, pred_usd: float) -> str | None:
    """Return currency with multiplier closest to ``price/pred_usd``.

    ``pred_usd`` is the predicted price in USD.  ``price`` is the numeric value
    provided by the user without a currency.  The function compares the implied
    multiplier ``price / pred_usd`` against the learnt exchange rates and picks
    the closest match.
    """

    if not rates or pred_usd <= 0 or not math.isfinite(pred_usd) or price <= 0:
        return None
    ratio = price / pred_usd
    best_cur = None
    best_diff = float("inf")
    for cur, mul in rates.items():
        diff = abs(ratio - mul)
        if diff < best_diff:
            best_diff = diff
            best_cur = cur
    return best_cur


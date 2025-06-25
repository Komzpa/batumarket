import math
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from price_utils import train_price_regression, predict_price, currency_rates, guess_currency


def test_train_and_predict():
    lots = [
        {'_id': 'a', 'price': 100, 'price:currency': 'USD'},
        {'_id': 'b', 'price': 200, 'price:currency': 'USD'},
    ]
    id_to_vec = {'a': [1.0, 0.0], 'b': [2.0, 0.0]}
    model, cur_map = train_price_regression(lots, id_to_vec)
    assert model is not None
    pred = predict_price(model, cur_map, [1.0, 0.0], 'USD')
    assert math.isclose(pred, 100.0, rel_tol=0.1)


def test_guess_currency():
    lots = [
        {'_id': 'a', 'price': 100, 'price:currency': 'USD'},
        {'_id': 'b', 'price': 200, 'price:currency': 'EUR'},
    ]
    id_to_vec = {'a': [1.0, 0.0], 'b': [1.0, 0.0]}
    model, cur_map = train_price_regression(lots, id_to_vec)
    rates = currency_rates(model, cur_map)
    pred = predict_price(model, cur_map, [1.0, 0.0], 'USD')
    guessed = guess_currency(rates, 200.0, pred)
    assert guessed == 'EUR'

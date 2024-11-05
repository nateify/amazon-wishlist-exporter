import json
import re
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlparse

import pytest
from babel.core import Locale, UnknownLocaleError
from price_parser import Price

from amazon_wishlist_exporter.utils.locale_ import (
    get_currency_from_territory,
    get_parsed_date,
    get_territory_from_tld,
)

# Amazon's launch
MIN_DATE = date(1995, 7, 16)

# Account for edge case when date is rounded up
MAX_DATE = date.today() + timedelta(days=1)

re_wishlist_parts = re.compile(r"\.amazon\.([a-z.]{2,})/.*?/wishlist.*/([A-Z0-9]{10,})[/?]?\b")


def validate_optional_string(value):
    return value is None or isinstance(value, str)


# Load test JSON files
def load_wishlist_data():
    testdata_dir = Path("./testdata")
    json_files = list(testdata_dir.rglob("*.json"))

    wishlist_data = []
    for json_file in json_files:
        with open(json_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            wishlist_data.append(data)

    return wishlist_data


@pytest.mark.parametrize("wishlist", load_wishlist_data())
def test_wishlist_structure(wishlist):
    # Optional strings
    optional_string_fields = ["title", "comment"]
    for field in optional_string_fields:
        assert validate_optional_string(wishlist[field])

    # ID
    assert isinstance(wishlist["id"], str)
    assert wishlist["id"].isalnum()

    # Valid URL
    assert bool(urlparse(wishlist["url"]).netloc)

    # Locale
    try:
        babel_locale = Locale.parse(wishlist["locale"])
        assert isinstance(babel_locale, Locale), "Expected an object of type 'Locale'"
    except (ValueError, TypeError, UnknownLocaleError) as e:
        assert False, f"Function raised an exception: {e}"


# Determine the language and currency for date and price parsing once per wishlist
def preproc_hints(wishlist):
    babel_language = Locale.parse(wishlist["locale"]).language
    wishlist_re_search = re.search(re_wishlist_parts, wishlist["url"])
    wishlist_tld = wishlist_re_search.group(1)
    territory_from_tld = get_territory_from_tld(wishlist_tld)
    currency_from_tld = get_currency_from_territory(territory_from_tld)

    return babel_language, currency_from_tld, wishlist["items"]


def gen_wishlist_item_param():
    wishlist_data = load_wishlist_data()
    param_data = []

    for wishlist in wishlist_data:
        babel_language, currency_from_tld, items = preproc_hints(wishlist)
        for item in items:
            param_data.append((babel_language, currency_from_tld, item))

    return param_data


@pytest.mark.parametrize("babel_language, currency_from_tld, item", gen_wishlist_item_param())
def test_wishlist_item_structure(babel_language, currency_from_tld, item):
    # Optional strings
    optional_string_fields = [
        "name",
        "asin",
        "link",
        "image",
        "comment",
        "date-added",
        "price",
        "old-price",
        "byline",
        "badge",
        "coupon",
    ]
    for field in optional_string_fields:
        assert validate_optional_string(item[field])

    # Category
    assert item["item-category"] in ["purchasable", "deleted", "external", "idea"]

    # ASIN
    if item["item-category"] in ["purchasable", "deleted"]:
        assert item["asin"]

    if item["asin"]:
        assert len(item["asin"]) == 10, "asin must be 10 characters long"
        assert item["asin"].isalnum(), "asin must be alphanumeric"

    # Item URL
    if item["item-category"] in ["purchasable", "external"]:
        assert item["link"]

    if item["link"]:
        assert bool(urlparse(item["link"]).netloc)

    # Price and old price
    for price_key in ["price", "old-price"]:
        if item[price_key] is not None:
            parsed_price = Price.fromstring(item[price_key], currency_hint=currency_from_tld)
            assert parsed_price.amount is not None, f"{price_key} should have a valid amount"
            assert isinstance(parsed_price.amount, Decimal), f"{price_key} amount should be a Decimal"
            assert validate_optional_string(parsed_price.currency)

    # Date added
    if item["date-added"] is not None:
        parsed_date = get_parsed_date(item["date-added"], babel_language)
        assert parsed_date is not None, "date-added should be a valid date"

        assert parsed_date.year is not None, "date-added should have a year"
        assert parsed_date.month is not None, "date-added should have a month"
        assert parsed_date.day is not None, "date-added should have a day"

        assert parsed_date >= MIN_DATE, "date-added is earlier than valid"
        assert parsed_date <= MAX_DATE, "date-added is in the future"

    # Rating data
    if item["item-category"] != "purchasable":
        assert item["rating"] is None
        assert item["total-ratings"] is None
    else:
        assert isinstance(item["rating"], float)
        assert item["rating"] >= 0.0
        assert item["rating"] <= 5.0

        assert isinstance(item["total-ratings"], int)
        assert item["total-ratings"] >= 0

    # Image URL
    if item["item-category"] == "purchasable":
        assert item["image"]

    if item["image"]:
        assert bool(urlparse(item["image"]).netloc)

    # Wants
    assert isinstance(item["wants"], int)
    assert item["wants"] >= 1

    # Has
    assert isinstance(item["has"], int)
    assert item["has"] >= 0

    # Item options such as color, size, etc
    if item["item-category"] != "purchasable":
        assert item["item-option"] is None
    else:
        assert item["item-option"] is None or isinstance(item["item-option"], dict)

    if item["item-option"]:
        assert bool(item["item-option"]), "item-option should not be an empty dict"

    # Coupon
    if item["coupon"]:
        assert any(char.isdigit() for char in item["coupon"]), "coupon should contain a digit"

    # Priority can be string or int between -2..2
    assert isinstance(item["priority"], (int, str))

    if isinstance(item["priority"], int):
        assert item["priority"] >= -2
        assert item["priority"] <= 2

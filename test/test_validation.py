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
earliest_valid_date = date(1995, 7, 16)

# Account for edge case rounding up from time zone close to international date line
today = date.today()
one_day_from_today = today + timedelta(days=1)

re_wishlist_parts = re.compile(r"\.amazon\.([a-z.]{2,})/.*?/wishlist.*/([A-Z0-9]{10,})[/?]?\b")


# Load test JSON files
@pytest.fixture
def wishlist_data():
    testdata_dir = Path("./testdata")
    json_files = list(testdata_dir.rglob("*.json"))

    wishlist_data = []
    for json_file in json_files:
        with open(json_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            wishlist_data.append(data)

    return wishlist_data


def validate_optional_string(value):
    return value is None or isinstance(value, str)


def test_wishlist_data(wishlist_data):
    for wishlist in wishlist_data:
        assert isinstance(wishlist["id"], str) and wishlist["id"].isalnum()

        assert validate_optional_string(wishlist["title"])

        assert validate_optional_string(wishlist["comment"])

        wishlist_locale = wishlist["locale"]

        try:
            babel_locale = Locale.parse(wishlist_locale)
            assert isinstance(babel_locale, Locale), "Expected an object of type 'Locale'"
        except (ValueError, TypeError, UnknownLocaleError) as e:
            assert False, f"Function raised an exception: {e}"

        # Valid URLs will have netloc when scheme is defined
        assert bool(urlparse(wishlist["url"]).netloc)

        # Used for date and price parsing hints
        babel_language = babel_locale.language
        wishlist_re_search = re.search(re_wishlist_parts, wishlist["url"])
        wishlist_tld = wishlist_re_search.group(1)
        territory_from_tld = get_territory_from_tld(wishlist_tld)
        currency_from_tld = get_currency_from_territory(territory_from_tld)

        for item in wishlist["items"]:
            assert item["item-category"] in ["purchasable", "deleted", "external", "idea"]

            assert validate_optional_string(item["name"])

            assert item["link"] is None or (bool(urlparse(item["link"]).netloc))

            assert validate_optional_string(item["asin"])

            # Validate ASIN
            if isinstance(item["asin"], str):
                assert len(item["asin"]) == 10, "asin must be 10 characters long"
                assert item["asin"].isalnum(), "asin must be alphanumeric"

            assert validate_optional_string(item["comment"])

            # Check "price" and "old-price" using price_parser
            for price_key in ["price", "old-price"]:
                if item[price_key] is not None:
                    parsed_price = Price.fromstring(item[price_key], currency_hint=currency_from_tld)
                    assert parsed_price.amount is not None, f"{price_key} should have a valid amount"
                    assert isinstance(parsed_price.amount, Decimal), f"{price_key} amount should be a Decimal"
                    assert validate_optional_string(parsed_price.currency)

            # Check "date-added" using dateparser
            if item["date-added"] is not None:
                parsed_date = get_parsed_date(item["date-added"], babel_language)
                assert parsed_date is not None, "date-added should be a valid date"

                assert parsed_date.year is not None, "date-added should have a year"
                assert parsed_date.month is not None, "date-added should have a month"
                assert parsed_date.day is not None, "date-added should have a day"

                assert parsed_date >= earliest_valid_date, "date-added is earlier than valid"
                assert parsed_date <= one_day_from_today, "date-added is in the future"

            assert item["rating"] is None or isinstance(item["rating"], float)

            if isinstance(item["rating"], float):
                assert item["rating"] >= 0.0

            assert item["total-ratings"] is None or isinstance(item["total-ratings"], int)

            if isinstance(item["total-ratings"], int):
                assert item["total-ratings"] >= 0

            assert item["image"] is None or (bool(urlparse(item["image"]).netloc))

            assert isinstance(item["wants"], int)
            assert item["wants"] >= 1

            assert isinstance(item["has"], int)
            assert item["has"] >= 0

            assert item["item-option"] is None or isinstance(item["item-option"], dict)

            if isinstance(item["item-option"], dict):
                assert bool(item["item-option"]), "item-option should not be an empty dict"

            assert validate_optional_string(item["byline"])

            assert validate_optional_string(item["badge"])

            assert validate_optional_string(item["coupon"])

            if isinstance(item["coupon"], str):
                assert any(char.isdigit() for char in item["coupon"]), "coupon should contain a digit"

            # Priority can be string or int between -2..2
            assert isinstance(item["priority"], (int, str))

            if isinstance(item["priority"], int):
                assert item["priority"] >= -2
                assert item["priority"] <= 2

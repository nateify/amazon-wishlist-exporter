import json
import warnings
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlparse

import pytest
from price_parser import Price

working_dir = Path(__file__).resolve().parent

HTML_JSON_DIR = working_dir / "testdata/json_from_html"
URL_JSON_DIR = working_dir / "testdata/json_from_url"


WISHLIST_META_KEYS = ["id", "title", "comment", "url", "locale", "language", "currency"]

EXACT_ITEM_KEYS = ["asin", "comment", "has", "priority", "wants"]
URL_KEYS = ["image", "link"]
ITEM_SAME_TYPE_KEYS = ["byline", "item-option", "name", "rating", "total-ratings", "price", "old-price"]
RATING_KEYS = ["rating", "total-ratings"]
PRICE_KEYS = ["price", "old-price"]

ITEM_MATCH_KEYS = ["asin", "image", "link", "name"]


def load_json(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_json_pairs():
    # Find matching JSON files between the HTML and URL directories
    html_files = {f.stem: f for f in HTML_JSON_DIR.glob("*.json")}
    url_files = {f.stem: f for f in URL_JSON_DIR.glob("*.json")}
    common_files = set(html_files.keys()) & set(url_files.keys())
    return [(html_files[stem], url_files[stem]) for stem in common_files]


def match_items_by_keys(html_items, url_items, keys):
    html_item_dicts = {key: {str(item.get(key)).lower(): item for item in html_items if item.get(key)} for key in keys}
    url_item_dicts = {key: {str(item.get(key)).lower(): item for item in url_items if item.get(key)} for key in keys}

    matched_pairs = []

    for key in keys:
        html_dict = html_item_dicts[key]
        url_dict = url_item_dicts[key]

        for html_key, html_item in list(html_dict.items()):
            if html_key in url_dict:
                matched_pairs.append((html_item, url_dict[html_key]))

    return matched_pairs


def get_from_multiple_keys(d, match_keys, default=None):
    return next((d.get(key, default) for key in match_keys if key in d), default)


@pytest.mark.parametrize("html_file, url_file", get_json_pairs())
def test_json_pair(html_file, url_file):
    # Load JSON data
    html_data = load_json(html_file)
    url_data = load_json(url_file)

    # Check that wishlist metadata is the same
    for key in WISHLIST_META_KEYS:
        html_value = html_data.get(key)
        url_value = url_data.get(key)
        if isinstance(html_value, str) and isinstance(url_value, str):
            # Convert both strings to lowercase for case-insensitive comparison
            assert html_value.lower() == url_value.lower(), (
                f"Exact match failed for key '{key}' in file '{html_file.name}'"
            )
        else:
            # Perform direct comparison for non-string types
            assert html_value == url_value, f"Exact match failed for key '{key}' in file '{html_file.name}'"

    currency = html_data["currency"]

    html_items = html_data.get("items", [])
    url_items = url_data.get("items", [])

    if len(html_items) != len(url_items):
        warnings.warn(f"Different item counts: HTML has {len(html_items)}, URL has {len(url_items)}")

    # Match items between the JSONs
    matched_pairs = match_items_by_keys(html_items, url_items, ITEM_MATCH_KEYS)

    for html_item, url_item in matched_pairs:
        # These values should be the same between locales
        for key in EXACT_ITEM_KEYS:
            html_value = html_item.get(key)
            url_value = url_item.get(key)
            if isinstance(html_value, str) and isinstance(url_value, str):
                # Convert both strings to lowercase for case-insensitive comparison
                assert html_value.lower() == url_value.lower(), (
                    f"Exact match failed for key '{key}' in file '{html_file.name}'"
                )
            else:
                # Perform direct comparison for non-string types
                assert html_value == url_value, f"Exact match failed for key '{key}' in file '{html_file.name}'"

        # URLs from Amazon are different between locales
        for key in URL_KEYS:
            html_value = html_item.get(key)
            url_value = url_item.get(key)

            assert isinstance(html_item[key], type(url_item[key])), (
                f"Type match failed for key '{key}' in file '{html_file.name}'"
            )

            if isinstance(html_value, str) and isinstance(url_value, str):
                html_url_parsed = urlparse(html_value)
                url_url_parsed = urlparse(url_value)

                html_category = html_item.get("item-category")
                url_category = url_item.get("item-category")

                # Ensures that both URLs are generally similar
                assert html_url_parsed.netloc == url_url_parsed.netloc, (
                    f"Netloc mismatch for key '{key}' in file '{html_file.name}'"
                )

                # External URLs should be exactly the same
                if html_category == "external" and url_category == "external":
                    assert html_url_parsed == url_url_parsed

        # Fixme: Edge case needs research
        html_category = html_item.get("item-category")
        url_category = url_item.get("item-category")
        assert any([
            html_category == url_category,  # Both are equal
            {"deleted", "purchasable"} == {html_category, url_category},
        ]), f"Mismatch in item-category: {html_category} != {url_category}"

        # These values will differ between locales
        for key in ITEM_SAME_TYPE_KEYS:
            assert isinstance(html_item[key], type(url_item[key])), (
                f"Type match failed for key '{key}' in file '{html_file.name}'"
            )

        # Ratings and price will only differ due to slight time differences between capturing data
        # Uses a 10% threshold which should ensure generally the items are matched and scraped properly
        for key in RATING_KEYS:
            html_value = html_item.get(key)
            url_value = url_item.get(key)
            if isinstance(html_value, (int, float)) and isinstance(url_value, (int, float)):
                html_value, url_value = float(html_value), float(url_value)
                tolerance = abs(html_value - url_value) <= 0.1 * max(html_value, url_value)
                assert tolerance, (
                    f"Failed {key} - {html_value} vs {url_value} - {html_file.name} - {get_from_multiple_keys(html_item, ITEM_MATCH_KEYS)}"
                )

        for key in PRICE_KEYS:
            html_value = html_item.get(key)
            url_value = url_item.get(key)

            if isinstance(html_value, str) and isinstance(url_value, str):
                html_value = Price.fromstring(html_value, currency_hint=currency).amount
                url_value = Price.fromstring(url_value, currency_hint=currency).amount

                tolerance = abs(html_value - url_value) <= Decimal("0.1") * max(html_value, url_value)
                assert tolerance, (
                    f"Failed {key} - {html_value} vs {url_value} - {html_file.name} - {get_from_multiple_keys(html_item, ITEM_MATCH_KEYS)}"
                )

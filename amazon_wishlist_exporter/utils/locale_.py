import re

from .logger_config import logger

try:
    import icu
except ImportError:
    logger.debug("PyICU not found - falling back to locale collation provided by system")
    from . import locale_collator as icu
from babel import Locale
from babel.dates import format_date
from babel.numbers import format_currency, get_territory_currencies
from dateparser import parse as parse_date
from dateparser.search import search_dates
from price_parser import parse_price

tld_to_locale_mapping = {
    "ca": ["en_ca", "fr_ca"],
    "com": ["en_us", "es_us"],
    "com.mx": ["es_mx"],
    "com.br": ["pt_br"],
    "es": ["es_es", "pt_pt", "en_gb"],
    "co.uk": ["en_gb"],
    "fr": ["fr_fr", "en_gb"],
    "nl": ["nl_nl", "en_gb"],
    "de": ["de_de", "en_gb", "cs_cz", "nl_nl", "pl_pl", "tr_tr", "da_dk"],
    "it": ["it_it", "en_gb"],
    "se": ["sv_se", "en_gb"],
    "pl": ["pl_pl"],
    "eg": ["ar_ae", "en_ae"],
    "com.tr": ["tr_tr"],
    "sa": ["ar_ae", "en_ae"],
    "ae": ["ar_ae", "en_ae"],
    "in": ["hi_in", "en_in", "ta_in", "te_in", "kn_in", "ml_in", "bn_in", "mr_in"],
    "sg": ["en_sg"],
    "com.au": ["en_au"],
    "co.jp": ["ja_jp", "en_us", "zh_cn"],
    "co.za": ["en_za"],
    "com.be": ["fr_be", "nl_be", "en_gb"],
}

special_tld_to_territory = {"com": "us", "co.uk": "gb"}

regex_date_added = {  # Missing bn_in, mr_in
    **dict.fromkeys(
        ["en_us", "en_ca"], re.compile(r"[^\d\s\u2025\u3000]+[\s\u2025\u3000]+(\w+[\s\u2025\u3000]\d+.*\d{4})")
    ),
    **dict.fromkeys(
        [
            "fr_fr",
            "fr_ca",
            "de_de",
            "cs_cz",
            "nl_nl",
            "pl_pl",
            "tr_tr",
            "da_dk",
            "en_gb",
            "es_us",
            "it_it",
            "es_es",
            "pt_pt",
            "en_au",
            "hi_in",
            "en_in",
            "te_in",
            "en_sg",
            "en_ae",
            "es_mx",
            "pt_br",
        ],
        re.compile(r"[^\d\s\u2025\u3000]+[\s\u2025\u3000]+(\d{1,2}\.?[\s\u2025\u3000].*\d{4})"),
    ),
    "ta_in": re.compile(r"^\D+[\s\u2025\u3000\W][\s\u2025\u3000](\d{1,2}[\s\u2025\u3000].*\d{4})$"),
    "kn_in": re.compile(r"([^\d\s\u2025\u3000]+[\s\u2025\u3000]\d{1,2},[\s\u2025\u3000]\d{4})"),
    "ml_in": re.compile(r"^(\d{4}[.,]?[\s\u2025\u3000].*\d{1,2})"),
    **dict.fromkeys(["ar_ae", "ar_sa"], re.compile(r"(\d{1,2}\D+\d{4})")),
    **dict.fromkeys(["ja_jp", "zh_cn"], re.compile(r"(\d{4}.*\d{1,2}日)")),
}


# Only some languages show "x out of 5" backwards
locale_to_rating_regex = {
    **dict.fromkeys(
        ["ja_jp", "hi_in", "ta_in", "te_in", "kn_in", "ml_in", "mr_in"],
        re.compile(r"^\d\D+[\s\u2025\u3000](\d(?:[.,]\d)?)$"),
    ),
    "default": re.compile(r"^\D*(\d(?:[.,]\d)?)\D"),
}


def normalize_tld(tld):
    return tld.lstrip(".").lower()


def normalize_locale(locale):
    return locale.replace("-", "_").lower()


def validate_tld_locale(store_tld, locale):
    store_tld = normalize_tld(store_tld)

    if store_tld not in tld_to_locale_mapping:
        raise ValueError(f"Invalid store TLD: '{store_tld}'. Must be one of {list(tld_to_locale_mapping.keys())}")

    valid_locales = tld_to_locale_mapping[store_tld]

    if locale.lower() not in valid_locales:
        raise ValueError(f"Invalid locale: '{locale}' for TLD: '{store_tld}'. Valid locales are: {valid_locales}")


def get_default_locale(store_tld):
    store_tld = normalize_tld(store_tld)
    valid_locales = tld_to_locale_mapping.get(store_tld)
    if not valid_locales:
        raise ValueError(f"Invalid store TLD: '{store_tld}'. Must be one of {list(tld_to_locale_mapping.keys())}")

    return valid_locales[0]  # Return the first locale in the list


def get_territory_from_tld(tld):
    # Check if TLD has a hardcoded mapping
    if tld in special_tld_to_territory:
        return special_tld_to_territory[tld]

    # If the TLD has a dot, use the part after the dot as the territory
    if "." in tld:
        return tld.split(".")[-1]

    # Otherwise, use the TLD itself as the territory
    return tld


def get_currency_from_territory(territory):
    try:
        # Get the currency for the determined territory
        currencies = get_territory_currencies(territory)

        if currencies:
            return currencies[0]  # Return the first currency in the list
        else:
            return None
    except Exception as e:
        logger.exception(f"Exception while retrieving currency for territory '{territory}': {e}")
        return None


def get_localized_price(text, currency, store_locale):
    parsed_price = parse_price(text, currency_hint=currency)

    return format_currency(parsed_price.amount, parsed_price.currency, locale=store_locale)


def get_parsed_date(text, babel_language):
    found_dates = search_dates(
        text,
        languages=[babel_language, "en"],
        settings={"PREFER_DATES_FROM": "past"},
    )

    if found_dates:
        try:
            return found_dates[0][1].date()
        except (IndexError, AttributeError):
            return None
    return None


def get_formatted_date(text, store_locale, date_as_iso8601):
    babel_language = Locale.parse(store_locale).language
    date_regex = regex_date_added.get(store_locale)

    parsed_date = None

    if date_regex:
        date_match = date_regex.search(text)
        if date_match:
            date_unparsed = date_match.group(1)
            parsed_date = parse_date(date_unparsed, languages=[babel_language, "en"])
            if parsed_date:
                parsed_date = parsed_date.date()
            else:
                text = date_unparsed

    if not parsed_date:
        parsed_date = get_parsed_date(text, babel_language)

    if date_as_iso8601:
        return parsed_date.isoformat() if parsed_date else None
    else:
        return format_date(parsed_date, format="long", locale=store_locale) if parsed_date else None


def get_rating_from_locale(rating_text, total_text, store_locale):
    rating_regex = locale_to_rating_regex.get(store_locale, locale_to_rating_regex["default"])
    totals_regex = re.compile(r"^\D*\b(\d[\s\u2025\u3000.,\d]*)\b")

    item_rating = item_match = rating_regex.search(rating_text)
    if item_match:
        rating = item_match.group(1)
        rating = re.sub(r"[\s\u2025\u3000,.]", ".", rating)
        item_rating = float(rating)

    total_ratings = total_match = totals_regex.search(total_text)
    if total_match:
        total = total_match.group(1)
        total = re.sub(r"[\s\u2025\u3000,.]", "", total)
        total_ratings = int(total)

    return item_rating, total_ratings


def sort_items(items, sort_keys, locale_string):
    locale_string = locale_string.lower().split("_")
    normalized_locale = f"{locale_string[0]}_{locale_string[1].upper()}.UTF-8"

    collator = icu.Collator.createInstance(icu.Locale(normalized_locale))

    # Prepare a list of valid keys
    valid_keys = set(items[0].keys()) if items else set()

    # Filter valid sort keys
    filtered_sort_keys = [key for key in sort_keys if key in valid_keys]

    def collate_and_sort(item):
        result = []
        for key in filtered_sort_keys:
            value = item[key]
            if isinstance(value, str):
                # Sort strings with locale-specific collation
                result.append((0, collator.getSortKey(value)))
            elif isinstance(value, (int, float)):
                # Sort numbers by largest to smallest (negative for reverse sort)
                result.append((1, -value))
            elif value is None:
                # Handle None values (sort them last)
                result.append((2, float("inf")))
            else:
                # Fallback behavior for other types
                result.append((3, float("inf")))
        return tuple(result)

    return sorted(items, key=collate_and_sort, reverse=False)

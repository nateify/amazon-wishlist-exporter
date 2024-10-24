import argparse
import re
from pathlib import Path
from .exporter import main

from .utils.locale_ import (
    get_default_locale,
    normalize_locale,
    normalize_tld,
    validate_tld_locale,
)


def re_group(match, group):
    try:
        return match.group(group)
    except (IndexError, AttributeError):
        return None


def cli():
    parser = argparse.ArgumentParser()

    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument("-i", "--id", type=str, help="Amazon wishlist ID")
    input_group.add_argument("-u", "--url", type=str, help="Amazon wishlist URL")
    input_group.add_argument("-f", "--html-file", "--html", type=str, help="Amazon wishlist HTML file")

    parser.add_argument("-t", "--store-tld", type=str, help="Amazon store TLD")
    parser.add_argument("-l", "--store-locale", "--locale", type=str, help="Amazon store locale")
    parser.add_argument(
        "-p",
        "--priority-is-localized",
        action="store_true",
        help="Priority is localized text instead of numeric value",
    )
    parser.add_argument(
        "-d", "--iso8601", action="store_true", help="Convert localized date strings to ISO 8601 format"
    )
    parser.add_argument("-s", "--sort-keys", type=str, help="Sort key(s) for JSON output")
    parser.add_argument("-c", "--compact-json", action="store_true", help="Write compacted JSON")
    parser.add_argument("-y", "--force", action="store_true", help="Overwrite existing output file without asking")
    parser.add_argument("-o", "--output-file", type=str, help="Output JSON file path")

    args = parser.parse_args()

    # Normalize the inputs
    if args.store_tld:
        args.store_tld = normalize_tld(args.store_tld)
    if args.store_locale:
        args.store_locale = normalize_locale(args.store_locale)

    # Logic for argument relationships
    if args.id:
        if not args.store_tld:
            parser.error("--store-tld is required when --id is provided")
        if not args.store_locale:
            args.store_locale = get_default_locale(args.store_tld)
        else:
            validate_tld_locale(args.store_tld, args.store_locale)

    elif args.url:
        re_amazon_wishlist_url = re.compile(r"\.amazon\.([a-z.]{2,})/.*?/wishlist.*/([A-Z0-9]{10,})[/?]?\b")
        url_parts = re.search(re_amazon_wishlist_url, args.url)
        matched_tld = re_group(url_parts, 1)
        matched_id = re_group(url_parts, 2)

        if matched_tld and matched_id:
            args.store_tld = matched_tld
            args.id = matched_id
        else:
            parser.error(f"Invalid URL input: {args.url}")

        if not args.store_locale:
            args.store_locale = get_default_locale(args.store_tld)
        else:
            validate_tld_locale(args.store_tld, args.store_locale)

    elif args.html_file:
        html_file_path = Path(args.html_file)
        re_amazon_html_name = re.compile(r"www\.amazon\.([a-z.]{2,})_\w+?_([A-z]{2}_[A-z]{2})")
        filename_parts = re.search(re_amazon_html_name, html_file_path.stem)
        matched_tld = re_group(filename_parts, 1)
        matched_locale = re_group(filename_parts, 2)

        if not html_file_path.is_file():
            parser.error("The provided HTML file path does not exist")

        if not args.store_tld:
            if not matched_tld:
                parser.error("Could not determine TLD from HTML file name and --store-tld was not provided")
            else:
                args.store_tld = matched_tld

        if not args.store_locale:
            if not matched_locale:
                parser.error("Could not determine locale from HTML file name and --store-locale was not provided")
            else:
                args.store_locale = matched_locale

        validate_tld_locale(args.store_tld, args.store_locale)

    main(args)
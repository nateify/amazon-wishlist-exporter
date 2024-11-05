import re
import sys
from pathlib import Path
from time import sleep

from amazon_wishlist_exporter.cli import cli
from amazon_wishlist_exporter.utils.locale_ import tld_to_locale_mapping

working_dir = Path(__file__).resolve().parent
urls_input = working_dir / "urls.txt"

re_wishlist_parts = re.compile(r"\.amazon\.([a-z.]{2,})/.*?/wishlist.*/([A-Z0-9]{10,})[/?]?\b")
re_basic_slug = re.compile(r"[^a-zA-Z0-9]+")


def generate_test_data(sample_wishlist_urls):
    args = ["-s", "asin,name", "-y", "--debug"]

    for url in sample_wishlist_urls:
        wishlist_re_search = re.search(re_wishlist_parts, url)
        wishlist_tld = wishlist_re_search.group(1)
        wishlist_id = wishlist_re_search.group(2)

        for locale in tld_to_locale_mapping.get(wishlist_tld):
            locale_reformat = locale.split("_")[0].lower() + "_" + locale.split("_")[1].upper()
            output_file_name = f"www.amazon.{wishlist_tld}_{wishlist_id}_{locale_reformat}"
            output_path = working_dir / "testdata/json_from_url" / f"{output_file_name}.json"

            sys.argv = ["cli.py"] + args + ["-u", url, "-l", locale, "-o", str(output_path)]

            cli()
            sleep(5)


if __name__ == "__main__":
    with open(urls_input, "r") as f:
        sample_wishlist_urls = [line.rstrip() for line in f]

    generate_test_data(sample_wishlist_urls)

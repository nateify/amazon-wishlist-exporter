import argparse
import json
from pathlib import Path

import re

from utils._locale import (
    get_default_locale,
    get_formatted_date,
    get_localized_price,
    get_rating_from_locale,
    normalize_locale,
    normalize_tld,
    sort_items,
    validate_tld_locale,
)
from utils.scraper import get_external_image, get_pages_from_local_file, get_pages_from_web


class WishlistItem(object):
    def __init__(self, element, id, store_tld, store_locale, base_url, priority_is_localized, date_as_iso8601):
        self.element = element
        self.id = id
        self.store_tld = store_tld
        self.store_locale = store_locale
        self.base_url = base_url
        self.priority_is_localized = priority_is_localized
        self.date_as_iso8601 = date_as_iso8601

    def item_action(self):
        element_action_button_class = self.element.xpath(
            ".//div[starts-with(@id,'itemAction_')]//span[starts-with(@id,'pab-') and not(starts-with(@id,'pab-declarative'))]/@class"
        )

        if not element_action_button_class:
            return "deleted"

        element_action_value = re.search(r"\s(wl.*$)", element_action_button_class[0].strip()).group(1)
        action_mapping = {
            "wl-info-aa_shop_this_store": "external",
            "wl-info-wl_kindle_ov_wfa_button": "idea",
        }
        return action_mapping.get(element_action_value, "purchasable")

    @property
    def is_deleted(self):
        return self.item_action() == "deleted"

    @property
    def is_external(self):
        return self.item_action() == "external"

    @property
    def is_idea(self):
        return self.item_action() == "idea"

    @property
    def name(self):
        if self.is_deleted:
            return None
        elif any((self.is_external, self.is_idea)):
            return self.element.xpath(".//span[starts-with(@id,'itemName_')]/text()")[0].strip()
        else:
            return self.element.xpath(".//a[starts-with(@id,'itemName_')]")[0].get("title")

    @property
    def link(self):
        if any((self.is_idea, self.is_deleted)):
            return None
        elif self.is_external:
            return self.element.xpath(
                ".//div[starts-with(@id,'itemAction_')]//div[contains(@class,'g-visible-no-js')]//a/@href"
            )[0]
        else:
            item_link = self.element.xpath(".//a[starts-with(@id,'itemName_')]")[0].get("href")
            if not item_link.startswith("http"):
                item_link = f"{self.base_url}{item_link}"
            return item_link

    @property
    def asin(self):
        if any((self.is_idea, self.is_external)):
            return None
        else:
            return re.search(r"ASIN:([A-z0-9]+)\|", self.element.get("data-reposition-action-params")).group(1)

    @property
    def comment(self):
        item_comment = self.element.xpath(".//span[starts-with(@id,'itemComment_')]/text()")[0].strip()
        if item_comment == "":  # Done to preserve json null functionality
            return None
        else:
            return item_comment

    @property
    def price(self):
        price_text = None
        if any((self.is_idea, self.is_deleted)):
            return price_text
        elif self.is_external:
            price_text = self.element.xpath(".//span[starts-with(@id,'itemPrice_')]/span[@class='a-offscreen']")[0].text
        else:
            item_price_primary_elem = self.element.xpath(
                ".//span[starts-with(@id,'itemPrice_')]/span[@class='a-offscreen']"
            )

            if item_price_primary_elem:
                price_text = item_price_primary_elem[0].text
            elif self.element.xpath("./@data-price")[0] == "-Infinity":  # Applies to out of stock items
                price_text = None
            else:
                # Applies to items which only have a marketplace price
                try:
                    price_text = self.element.xpath(".//span[contains(@class,'itemUsedAndNewPrice')]/text()")[0].strip()
                except IndexError:
                    # Usually when no Buy Box is available
                    price_text = None

        if price_text:
            return get_localized_price(price_text, self.store_tld, self.store_locale)

    @property
    def old_price(self):
        if any((self.is_idea, self.is_external, self.is_deleted)):
            return None
        else:
            # Amazon does not always show this value
            item_old_price_elem = self.element.xpath(".//div[contains(@class,'itemPriceDrop')]")
            if not item_old_price_elem:
                return None
            else:
                item_old_price_text = item_old_price_elem[0].xpath(".//span[not(@*)]/text()")[0].strip()

                return get_localized_price(item_old_price_text, self.store_tld, self.store_locale)

    @property
    def date_added(self):
        try:
            item_date_added_full = self.element.xpath(".//span[starts-with(@id,'itemAddedDate_')]/text()")[0].strip()
        except IndexError:
            return None

        return get_formatted_date(item_date_added_full, self.store_locale, self.date_as_iso8601)

    @property
    def priority(self):
        item_priority_text = self.element.xpath(".//span[starts-with(@id,'itemPriorityLabel_')]/text()")[0].strip()
        item_priority_numerical = int(self.element.xpath(".//span[starts-with(@id,'itemPriority_')]/text()")[0].strip())

        if self.priority_is_localized:
            return item_priority_text
        else:
            return item_priority_numerical

    @property
    def ratings_data(self):
        if any((self.is_idea, self.is_external, self.is_deleted)):
            return None, None
        else:
            item_rating_elem = self.element.xpath(".//a[contains(@href,'/product-reviews/') and not(@id)]/@aria-label")

            # Some Amazon products can have 0 ratings
            if item_rating_elem:
                item_rating_text = item_rating_elem[0]
                item_total_ratings_text = self.element.xpath(".//a[starts-with(@id,'review_count_')]/text()")[0].strip()

                item_rating, item_total_ratings = get_rating_from_locale(
                    item_rating_text, item_total_ratings_text, self.store_locale
                )
            else:
                item_rating = item_total_ratings = None

            return item_rating, item_total_ratings

    @property
    def rating(self):
        return self.ratings_data[0]

    @property
    def total_ratings(self):
        return self.ratings_data[1]

    @property
    def image(self):
        if any((self.is_idea, self.is_deleted)):
            return None
        elif self.is_external:
            item_image = self.element.xpath(".//div[starts-with(@id,'itemImage_')]/img/@src")[0]

            # If Amazon does not have an image stored, we will try to find the open graph image
            if re.search(r"[./-].*amazon\.\w{2,}\/.*wishlist.*no_image_", item_image):
                item_image = get_external_image(self.link)

            return item_image

        else:
            return self.element.xpath(".//div[starts-with(@id,'itemImage_')]//img/@src")[0]

    @property
    def wants(self):
        return int(self.element.xpath(".//span[starts-with(@id,'itemRequested_')]/text()")[0].strip())

    @property
    def has(self):
        return int(self.element.xpath(".//span[starts-with(@id,'itemPurchased_')]/text()")[0].strip())

    def asdict(self):
        return_dict = {
            "name": self.name,
            "link": self.link,
            "asin": self.asin,
            "comment": self.comment,
            "price": self.price,
            "old-price": self.old_price,
            "date-added": self.date_added,
            "priority": self.priority,
            "rating": self.rating,
            "total-ratings": self.total_ratings,
            "image": self.image,
            "wants": self.wants,
            "has": self.has,
            "is-external": self.is_external,
            "is-idea": self.is_idea,
            "is-deleted": self.is_deleted,
        }

        # Fix NBSP character
        for key, value in return_dict.items():
            if isinstance(value, str):
                return_dict[key] = value.replace("\u00a0", " ")

        return return_dict


class Wishlist(object):
    item_class = WishlistItem

    def __init__(
        self,
        wishlist_id=None,
        html_file=None,
        store_tld=None,
        store_locale=None,
        priority_is_localized=False,
        date_as_iso8601=False,
    ):
        self.wishlist_id = wishlist_id
        self.html_file = html_file
        self.store_tld = store_tld
        self.store_locale = store_locale
        self.priority_is_localized = priority_is_localized
        self.date_as_iso8601 = date_as_iso8601

        self.base_url = f"https://www.amazon.{self.store_tld}"

        if not self.html_file:
            self.all_pages_html = get_pages_from_web(self.base_url, self.wishlist_url)
        else:
            self.all_pages_html = get_pages_from_local_file(self.html_file)

        self.first_page_html = self.all_pages_html[0] if self.all_pages_html else None

    @property
    def id(self):
        if not self.wishlist_id:
            return self.first_page_html.xpath("//input[@id='listId']/@value")[0].strip()
        else:
            return self.wishlist_id

    @property
    def wishlist_title(self):
        wishlist_title = self.first_page_html.xpath("//span[@id='profile-list-name']/text()")

        if wishlist_title:
            return wishlist_title[0].strip()
        else:
            return None

    @property
    def wishlist_comment(self):
        wishlist_comment = self.first_page_html.xpath("//span[@id='wlDesc']/text()")

        if wishlist_comment:
            return wishlist_comment[0].strip()
        else:
            return None

    @property
    def wishlist_url(self):
        return f"{self.base_url}/hz/wishlist/ls/{self.id}?language={self.store_locale}&viewType=list"

    @property
    def wishlist_details(self):
        return {
            "wishlist-id": self.id,
            "wishlist-title": self.wishlist_title,
            "wishlist-comment": self.wishlist_comment,
            "locale": self.store_locale,
            "wishlist-url": self.wishlist_url,
        }

    @property
    def wishlist_items(self):
        for page in self.all_pages_html:
            items_list = page.xpath("//li[contains(@class,'g-item-sortable')]")

            for item_element in items_list:
                yield self.item_class(
                    item_element,
                    self.wishlist_id,
                    self.store_tld,
                    self.store_locale,
                    self.base_url,
                    self.priority_is_localized,
                    self.date_as_iso8601,
                )

    def __iter__(self):
        for item in self.wishlist_items:
            yield item.asdict()


def main(args):
    if args.html_file:
        parsed_path = str(Path(args.html_file).resolve())
        w = Wishlist(
            html_file=parsed_path,
            store_tld=args.store_tld,
            store_locale=args.store_locale,
            priority_is_localized=args.priority_is_localized,
            date_as_iso8601=args.iso8601,
        )
    else:
        w = Wishlist(
            wishlist_id=args.id,
            store_tld=args.store_tld,
            store_locale=args.store_locale,
            priority_is_localized=args.priority_is_localized,
            date_as_iso8601=args.iso8601,
        )

    wishlist_items = []

    for i in w:
        wishlist_items.append(i)

    wishlist_full = w.wishlist_details

    if args.sort_keys:
        sort_keys = [key.strip() for key in args.sort_keys.split(",")]
        wishlist_items = sort_items(wishlist_items, sort_keys, args.store_locale)

    wishlist_full["items"] = wishlist_items

    indent = None if args.compact_json else 2

    if args.output_file:
        p = Path(args.output_file)

        if not p.parent.is_dir():
            mkdir = input(f"Directory {p.parent} does not exist. Create it? y/n: ")
            if mkdir.lower() != "y":
                exit(1)
            else:
                p.parent.mkdir(exist_ok=True, parents=True)

        if p.is_file() and not args.force:
            overwrite = input(f"{p} already exists. Overwrite? y/n: ")
            if overwrite.lower() != "y":
                exit(1)

        with open(p, mode="w", encoding="utf-8") as f:
            json.dump(wishlist_full, f, indent=indent, ensure_ascii=False)

        print(f"JSON written to {p.resolve()}")
    else:
        print(json.dumps(wishlist_full, indent=indent, ensure_ascii=False))


def cli():
    parser = argparse.ArgumentParser()

    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument("-i", "--id", type=str, help="Amazon wishlist ID")
    input_group.add_argument("-f", "--html-file", type=str, help="Amazon wishlist HTML file")

    parser.add_argument("-t", "--store-tld", type=str, help="Amazon store TLD")
    parser.add_argument("-l", "--store-locale", "--locale", type=str, help="Amazon store locale")
    parser.add_argument(
        "-p",
        "--priority-is-localized",
        action="store_true",
        help="Return localized priority text instead of numeric value",
    )
    parser.add_argument(
        "-d", "--iso8601", action="store_true", help="Convert localized date strings to ISO 8601 format"
    )
    parser.add_argument("-s", "--sort-keys", type=str, help="Sort key(s) for JSON output")
    parser.add_argument("-c", "--compact-json", action="store_true", help="Write compacted JSON")
    parser.add_argument("-y", "--force", action="store_true", help="Overwrite existing output file without asking")
    parser.add_argument("-o", "--output-file", type=str, help="Output JSON file")

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

        # If locale is not provided, fetch the default one
        if not args.store_locale:
            args.store_locale = get_default_locale(args.store_tld)
        else:
            # Validate the provided locale
            validate_tld_locale(args.store_tld, args.store_locale)

    elif args.html_file:
        # Both store-tld and locale are required
        if not args.store_tld:
            parser.error("--store-tld is required when --html-file is provided")
        if not args.store_locale:
            parser.error("--locale is required when --html-file is provided")

        if not Path(args.html_file).is_file():
            parser.error("The provided HTML file path does not exist")

        # Validate the provided locale
        validate_tld_locale(args.store_tld, args.store_locale)

    main(args)


if __name__ == "__main__":
    cli()

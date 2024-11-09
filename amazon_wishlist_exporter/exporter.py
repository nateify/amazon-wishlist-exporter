import json
import re
from pathlib import Path

from babel.core import Locale

from .utils.locale_ import (
    get_currency_from_territory,
    get_formatted_date,
    get_localized_price,
    get_rating_from_locale,
    get_territory_from_tld,
    sort_items,
)
from .utils.logger_config import logger
from .utils.scraper import (
    get_attr_value,
    get_external_image,
    get_node_text,
    get_pages_from_local_file,
    get_pages_from_web,
)


class WishlistItem:
    def __init__(self, element, **config):
        self.element = element
        self.store_locale = config.get("store_locale").lower()
        self.base_url = config.get("base_url")
        self.priority_is_localized = config.get("priority_is_localized", False)
        self.date_as_iso8601 = config.get("date_as_iso8601", False)
        self.wishlist_currency = config.get("wishlist_currency")

    @property
    def item_category(self):
        element_action_button = self.element.css_first(
            "div[id^='itemAction_'] span[id^='pab-']:not([id^='pab-declarative'])"
        )
        element_action_button_class = get_attr_value(element_action_button, "class")

        if not element_action_button_class:
            return "deleted"

        element_action_value = re.search(r"\s(wl.*$)", element_action_button_class).group(1)
        action_mapping = {
            "wl-info-aa_shop_this_store": "external",
            "wl-info-wl_kindle_ov_wfa_button": "idea",
        }
        return action_mapping.get(element_action_value, "purchasable")

    def is_purchasable(self):
        return self.item_category == "purchasable"

    def is_deleted(self):
        return self.item_category == "deleted"

    def is_external(self):
        return self.item_category == "external"

    def is_idea(self):
        return self.item_category == "idea"

    @property
    def name(self):
        if self.is_deleted():
            return None
        elif any((self.is_external(), self.is_idea())):
            return self.element.css_first("span[id^='itemName_']").text(strip=True)
        else:
            return get_attr_value(self.element.css_first("a[id^='itemName_']"), "title")

    @property
    def link(self):
        if any((self.is_idea(), self.is_deleted())):
            return None
        elif self.is_external():
            return get_attr_value(self.element.css_first("div[id^='itemAction_'] div.g-visible-no-js a"), "href")
        else:
            item_link = get_attr_value(self.element.css_first("a[id^='itemName_']"), "href")
            if not item_link.startswith("http"):
                item_link = f"{self.base_url}{item_link}"
            return item_link

    @property
    def asin(self):
        if any((self.is_idea(), self.is_external())):
            return None
        else:
            return re.search(r"ASIN:([A-z0-9]+)\|", self.element.attributes["data-reposition-action-params"]).group(1)

    @property
    def comment(self):
        item_comment = self.element.css_first("span[id^='itemComment_']").text(strip=True)
        if item_comment == "":  # Done to preserve json null functionality
            return None
        else:
            return item_comment

    @property
    def price(self):
        price_text = None

        if any((self.is_idea(), self.is_deleted())):
            return price_text

        price_elem = self.element.css_first("span[id^='itemPrice_'] > span.a-offscreen")

        if self.is_external():
            price_text = price_elem.text(strip=True)
        else:
            if price_elem:
                price_text = price_elem.text(strip=True)
            elif (
                get_attr_value(self.element.css_first("[data-price]"), "data-price") == "-Infinity"
            ):  # Applies to out of stock items
                price_text = None
            else:
                # Applies to items which only have a marketplace price
                try:
                    price_text = self.element.css_first("span[class*='itemUsedAndNewPrice']").text(strip=True)
                except AttributeError:
                    # Usually when no Buy Box is available
                    price_text = None

        if price_text:
            return get_localized_price(price_text, self.wishlist_currency, self.store_locale)

    @property
    def old_price(self):
        if not self.is_purchasable():
            return None
        else:
            # Amazon does not always show this value
            item_old_price_elem = self.element.css_first("div[class*='itemPriceDrop']")
            if not item_old_price_elem:
                return None
            else:
                item_old_price_text = next(
                    n.text(strip=True) for n in item_old_price_elem.css("span") if len(n.attributes) == 0
                )

                return get_localized_price(item_old_price_text, self.wishlist_currency, self.store_locale)

    @property
    def date_added(self):
        try:
            item_date_added_full = self.element.css_first("span[id^='itemAddedDate_']").text(strip=True)
        except AttributeError:
            return None

        return get_formatted_date(item_date_added_full, self.store_locale, self.date_as_iso8601)

    @property
    def priority(self):
        item_priority_text = self.element.css_first("span[id^='itemPriorityLabel_']").text(strip=True)

        item_priority_text = item_priority_text.split("\n")[-1].strip()
        item_priority_numerical = int(self.element.css_first("span[id^='itemPriority_']").text(strip=True))

        if self.priority_is_localized:
            return item_priority_text
        else:
            return item_priority_numerical

    def ratings_data(self):
        if not self.is_purchasable():
            return None, None
        else:
            item_rating_text = get_attr_value(
                self.element.css_first("a[href*='/product-reviews/']:not([id])"), "aria-label"
            )

            # Some Amazon products can have 0 ratings
            if item_rating_text:
                item_total_ratings_text = self.element.css_first("a[id^='review_count_']").text(strip=True)

                item_rating, item_total_ratings = get_rating_from_locale(
                    item_rating_text, item_total_ratings_text, self.store_locale
                )
            else:
                item_rating = 0.0
                item_total_ratings = 0

            return item_rating, item_total_ratings

    @property
    def rating(self):
        return self.ratings_data()[0]

    @property
    def total_ratings(self):
        return self.ratings_data()[1]

    @property
    def image(self):
        if any((self.is_idea(), self.is_deleted())):
            return None

        img_elem = self.element.css_first("div[id^='itemImage_'] img")
        img_src = get_attr_value(img_elem, "src")

        # If Amazon does not have an image stored, we will try to find the open graph image
        if self.is_external() and re.search(r"[./-].*amazon\.\w{2,}/.*wishlist.*no_image_", img_src):
            img_src = get_external_image(self.link)

        return img_src

    @property
    def wants(self):
        return int(self.element.css_first("span[id^='itemRequested_']").text(strip=True))

    @property
    def has(self):
        return int(self.element.css_first("span[id^='itemPurchased_']").text(strip=True))

    @property
    def item_option(self):
        twister_text_elem = self.element.css("span#twisterText")
        options_dict = {}

        for node in twister_text_elem:
            node_pairs = [x.strip() for x in node.text().split(" : ")]
            options_dict[node_pairs[0]] = node_pairs[1]

        return options_dict if options_dict else None

    @property
    def byline(self):
        if not self.is_purchasable():
            return None
        else:
            return self.element.css_first("span[id^='item-byline']").text(strip=True)

    @property
    def badge(self):
        badge_elem = self.element.css_first('span[id^="itemBadge_"][id$="-label"]')

        if badge_elem:
            badge_label = badge_elem.text(strip=True)
            badge_sup = badge_elem.parent.css_first('span[id$="-supplementary"]').text(strip=True)
            # todo: check other locales
            return f"{badge_label} {badge_sup}"
        else:
            return None

    @property
    def coupon(self):
        coupon_elem = self.element.css_first("i[id^='coupon-badge_']")

        if coupon_elem:
            return coupon_elem.text(strip=True)
        else:
            return None

    def asdict(self):
        return_dict = {
            name.replace("_", "-"): getattr(self, name)
            for name in dir(self.__class__)
            if isinstance(getattr(self.__class__, name), property)
        }

        # Whitespace fixer
        for k, v in return_dict.items():
            if isinstance(v, str):
                v = re.sub(r"[\s\u2025\u3000]", " ", v)
                return_dict[k] = v if v != "" else None

        return return_dict


class Wishlist:
    item_class = WishlistItem

    def __init__(
        self,
        wishlist_id=None,
        html_file=None,
        store_tld=None,
        store_locale=None,
        priority_is_localized=False,
        date_as_iso8601=False,
        test_output=False,
    ):
        self.wishlist_id = wishlist_id
        self.html_file = html_file
        self.store_tld = store_tld
        self.store_locale = store_locale
        self.priority_is_localized = priority_is_localized
        self.date_as_iso8601 = date_as_iso8601
        self.test_output = test_output

        self.base_url = f"https://www.amazon.{self.store_tld}"

        if not self.html_file:
            self.all_pages_html = get_pages_from_web(
                self.base_url, self.wishlist_url, self.wishlist_babel_locale, self.wishlist_currency
            )
        else:
            self.all_pages_html = get_pages_from_local_file(self.html_file)

        self.first_page_html = self.all_pages_html[0] if self.all_pages_html else None

    @property
    def id(self):
        if self.wishlist_id:
            return self.wishlist_id
        else:
            return get_attr_value(self.first_page_html.css_first("#listId"), "value")

    @property
    def wishlist_title(self):
        wishlist_title = get_node_text(self.first_page_html.css_first("span#profile-list-name"))

        return wishlist_title

    @property
    def wishlist_comment(self):
        wishlist_comment = get_node_text(self.first_page_html.css_first("span#wlDesc"))

        return wishlist_comment

    @property
    def wishlist_url(self):
        return f"{self.base_url}/hz/wishlist/ls/{self.id}?language={self.wishlist_babel_locale}&viewType=list"

    @property
    def wishlist_babel_locale(self):
        return Locale.parse(self.store_locale)

    @property
    def wishlist_babel_language(self):
        return self.wishlist_babel_locale.language

    @property
    def wishlist_currency(self):
        territory_from_tld = get_territory_from_tld(self.store_tld)
        currency_from_tld = get_currency_from_territory(territory_from_tld)

        return currency_from_tld

    @property
    def config(self):
        return {
            "store_locale": self.store_locale,
            "base_url": self.base_url,
            "priority_is_localized": self.priority_is_localized,
            "date_as_iso8601": self.date_as_iso8601,
            "wishlist_babel_locale": self.wishlist_babel_locale,
            "wishlist_babel_language": self.wishlist_babel_language,
            "wishlist_currency": self.wishlist_currency,
        }

    def __iter__(self):
        for page in self.all_pages_html:
            items_list = page.css('li[class*="g-item-sortable"]')
            for item_element in items_list:
                yield self.item_class(item_element, **self.config).asdict()

    @property
    def items(self):
        return list(iter(self))

    @property
    def wishlist_details(self):
        details = {
            "id": self.id,
            "title": self.wishlist_title,
            "comment": self.wishlist_comment,
            "url": self.wishlist_url,
            "locale": self.store_locale,
            "items": self.items,
        }
        if self.test_output:
            details["language"] = self.wishlist_babel_language
            details["currency"] = self.wishlist_currency

        return details


def main(args):
    wishlist_args = {
        "store_tld": args.store_tld,
        "store_locale": args.store_locale,
        "priority_is_localized": args.priority_is_localized,
        "date_as_iso8601": args.iso8601,
        "test_output": args.test,
    }

    if args.html_file:
        wishlist_args["html_file"] = str(Path(args.html_file).resolve())
    else:
        wishlist_args["wishlist_id"] = args.id

    w = Wishlist(**wishlist_args)

    wishlist_full = w.wishlist_details
    wishlist_items = wishlist_full["items"]

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

        logger.info(f"JSON written to {p.resolve()}")
    else:
        print(json.dumps(wishlist_full, indent=indent, ensure_ascii=False))

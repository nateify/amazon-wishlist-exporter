import json
from time import sleep

from amazoncaptcha import AmazonCaptcha
from babel import Locale
from curl_cffi import requests
from selectolax.lexbor import LexborHTMLParser

from .locale_ import get_currency_from_territory, get_territory_from_tld
from .logger_config import logger


def get_attr_value(node, node_attr):
    if hasattr(node, "attributes") and isinstance(node.attributes, dict):
        value = node.attributes.get(node_attr)
        if isinstance(value, str):
            return value.strip()
        return value

    return None


def get_node_text(node):
    node_text = None

    if node:
        node_text = node.text(strip=True)

    return node_text


def extract_pagination_details(page_html):
    pagination_elem = page_html.css_first('script[data-a-state=\'{"key":"scrollState"}\']')
    if pagination_elem:
        pagination_details = json.loads(pagination_elem.text())
        return pagination_details
    return None


def get_external_image(link):
    logger.debug(f"Retrieving canonical image from external link {link}")

    external_image_session = requests.Session(impersonate="chrome")

    external_r = external_image_session.get(link, headers={"Referer": "https://www.amazon.com/"})

    tree = LexborHTMLParser(external_r.content)
    head = tree.head

    og_image = get_attr_value(head.css_first("meta[property='og:image']"), "content")
    if og_image:
        return og_image

    twitter_image = get_attr_value(head.css_first("meta[name='twitter:image']"), "content")
    if twitter_image:
        return twitter_image

    link_image_src = get_attr_value(head.css_first("link[rel='image_src']"), "href")
    if link_image_src:
        return link_image_src

    microdata_attrs = getattr(head.css_first("*[itemprop='image']"), "attributes", None)
    microdata_image = next((microdata_attrs[k] for k in ("content", "src") if k in microdata_attrs), None)
    if microdata_image:
        return microdata_image

    schema_image_json = tree.select("script").text_contains("schema").matches
    for schema_json in schema_image_json:
        try:
            schema_data = json.loads(schema_json.text())
            if isinstance(schema_data, dict) and "image" in schema_data:
                # In case 'image' is a list or a single string, return the first URL
                if isinstance(schema_data["image"], list):
                    return schema_data["image"][0]
                return schema_data["image"]
        except json.JSONDecodeError:
            continue  # Skip if not valid JSON

    logger.debug(f"No canonical image determined for {link}")
    return None


def generate_locale_request_components(store_tld, store_locale):
    territory_from_tld = get_territory_from_tld(store_tld)
    currency_from_tld = get_currency_from_territory(territory_from_tld)

    babel_locale = Locale.parse(store_locale)

    primary_locale = str(babel_locale).replace("_", "-")
    backup_locale = babel_locale.language
    formatted_locales = [primary_locale, f"{backup_locale};0.9"]
    formatted_string = ", ".join(formatted_locales)

    headers_dict = {"Accept-Language": formatted_string}

    cookies_dict = {"i18n-prefs": currency_from_tld, "lc-acbin": str(babel_locale)}

    return headers_dict, cookies_dict


def get_pages_from_web(base_url, wishlist_url, store_tld, store_locale):
    # Required to get web page to return the correct formatting
    locale_headers, locale_cookies = generate_locale_request_components(store_tld, store_locale)

    wishlist_pages = []

    s = requests.Session(impersonate="chrome", cookies=locale_cookies, headers=locale_headers)
    logger.debug(f"Requesting {wishlist_url}")
    initial_request = s.get(wishlist_url)
    tree = LexborHTMLParser(initial_request.content)

    captcha_element = tree.css_first("form[action='/errors/validateCaptcha']")
    if captcha_element:
        logger.debug("Captcha was hit. Attempting to solve...")
        tree = solve_captcha(s, base_url, tree, wishlist_url)

    wishlist_pages.append(tree)

    # Handle pagination
    pagination_details = extract_pagination_details(tree)

    while pagination_details and pagination_details["lastEvaluatedKey"]:
        next_page_url = f"{base_url}{pagination_details['showMoreUrl']}"
        sleep(3)  # Slightly prevent anti-bot measures
        logger.debug(f"Requesting paginated URL {next_page_url}")
        r = s.get(next_page_url)
        current_page = LexborHTMLParser(r.content)
        wishlist_pages.append(current_page)
        pagination_details = extract_pagination_details(current_page)

    return wishlist_pages


def get_pages_from_local_file(html_file):
    with open(html_file, encoding="utf-8") as f:
        html = f.read()

    tree = LexborHTMLParser(html)
    page = tree.root

    if not page.css_matches("div#endOfListMarker"):
        logger.warning("HTML file does not contain endOfListMarker")

    return [page]


def solve_captcha(session, base_url, input_tree, wishlist_url, max_retries=3):
    captcha_link = get_attr_value(
        input_tree.css_first("img[src^='https://images-na.ssl-images-amazon.com/captcha']"), "src"
    )
    hidden_value = get_attr_value(input_tree.css_first("input[name='amzn']"), "value")

    if not captcha_link or not hidden_value:
        raise Exception("Captcha elements not found on the page.")

    captcha = AmazonCaptcha.fromlink(captcha_link)

    for attempt in range(max_retries):
        solution = captcha.solve()
        if not solution:
            raise Exception("Failed to solve captcha.")
        logger.debug("Captcha solved, sleeping 3 seconds")

        validate_captcha_url = f"{base_url}/errors/validateCaptcha"
        params = {
            "amzn": hidden_value,
            "amzn-r": "/",
            "field-keywords": solution,
        }

        sleep(3)  # Slightly prevent anti-bot measures
        response = session.get(url=validate_captcha_url, params=params)

        if response.status_code == 200:
            logger.debug("Successfully validated captcha URL")
            # Retry loading the wishlist page after captcha validation
            retry_page_response = session.get(wishlist_url)
            if retry_page_response.status_code == 200:
                logger.debug("Successfully requested wishlist page after captcha")
                return LexborHTMLParser(retry_page_response.content)
        else:
            logger.debug(f"Captcha solution attempt {attempt + 1} failed. Retrying...")

    raise Exception(f"Failed to solve captcha after {max_retries} attempts.")

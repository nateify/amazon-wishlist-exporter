import json
from time import sleep

from amazoncaptcha import AmazonCaptcha
from curl_cffi import requests
from selectolax.lexbor import LexborHTMLParser
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_result,
    stop_after_attempt,
    stop_after_delay,
    wait_fixed,
    wait_random,
)

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


@retry(wait=wait_fixed(3) + wait_random(0, 2), stop=stop_after_delay(10), before_sleep=before_sleep_log(logger, 30))
def get_with_retry(session, url, **kwargs):
    logger.debug(f"Requesting {url}")
    response = session.get(url, **kwargs)
    response.raise_for_status()
    return response


def extract_pagination_details(page_html):
    pagination_elem = page_html.css_first('script[data-a-state=\'{"key":"scrollState"}\']')
    if pagination_elem:
        pagination_details = json.loads(pagination_elem.text())
        return pagination_details
    return None


def get_external_image(link):
    logger.debug(f"Retrieving canonical image from external link {link}")

    external_image_session = requests.Session(impersonate="chrome")

    external_r = get_with_retry(external_image_session, link, headers={"Referer": "https://www.amazon.com/"})

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


def generate_locale_request_components(babel_locale, babel_currency):
    primary_locale = str(babel_locale).replace("_", "-")
    backup_locale = babel_locale.language
    formatted_locales = [primary_locale, f"{backup_locale};0.9"]
    formatted_string = ", ".join(formatted_locales)

    headers_dict = {"Accept-Language": formatted_string}

    cookies_dict = {"i18n-prefs": babel_currency, "lc-acbin": str(babel_locale)}

    return headers_dict, cookies_dict


def get_pages_from_web(base_url, wishlist_url, babel_locale, babel_currency):
    # Required to get web page to return the correct formatting
    locale_headers, locale_cookies = generate_locale_request_components(babel_locale, babel_currency)

    wishlist_pages = []

    s = requests.Session(impersonate="chrome", cookies=locale_cookies, headers=locale_headers)
    logger.debug(f"Requesting {wishlist_url}")
    # initial_request = s.get(wishlist_url)
    initial_request = get_with_retry(s, wishlist_url)
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
        # r = s.get(next_page_url)
        r = get_with_retry(s, next_page_url)
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


def solve_captcha(session, base_url, input_tree, wishlist_url):
    @retry(
        wait=wait_fixed(5) + wait_random(2, 5),
        stop=stop_after_attempt(5),
        retry=(retry_if_result(lambda result: result is None)),
        before_sleep=before_sleep_log(logger, 10),
    )
    def attempt_solve():
        # Fetch captcha link and hidden value from the input tree
        captcha_link = get_attr_value(
            input_tree.css_first("img[src^='https://images-na.ssl-images-amazon.com/captcha']"), "src"
        )
        hidden_value = get_attr_value(input_tree.css_first("input[name='amzn']"), "value")

        if not captcha_link or not hidden_value:
            logger.warning("Captcha elements not found on the page. Retrying...")
            return None  # Trigger retry if elements are missing

        # Solve the captcha
        captcha = AmazonCaptcha.fromlink(captcha_link)
        solution = captcha.solve()
        if not solution:
            logger.warning("Failed to solve captcha. Retrying...")
            return None  # Trigger retry if no solution is found

        logger.debug("Captcha solved, sleeping 3 seconds")
        sleep(3)  # Slight delay to prevent bot detection

        # Attempt to validate captcha
        validate_captcha_url = f"{base_url}/errors/validateCaptcha"
        params = {
            "amzn": hidden_value,
            "amzn-r": "/",
            "field-keywords": solution,
        }
        response = session.get(url=validate_captcha_url, params=params)

        response.raise_for_status()

        logger.debug("Successfully validated captcha URL")
        return True  # Proceed if captcha validation is successful

    # Run the solve attempt with retries
    try:
        if attempt_solve():
            # Retry loading the wishlist page after captcha validation
            wishlist_response = get_with_retry(session, wishlist_url)
            if wishlist_response:
                logger.debug("Successfully requested wishlist page after captcha")
                return LexborHTMLParser(wishlist_response.content)
    except Exception as e:
        logger.error(f"Failed to solve captcha: {e}")
        raise Exception("Failed to solve captcha after maximum attempts")

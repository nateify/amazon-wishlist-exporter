import ast
import json
from time import sleep

from amazoncaptcha import AmazonCaptcha
from curl_cffi import requests
from lxml import etree, html
from selectolax.lexbor import LexborHTMLParser

from .logger_config import logger


def get_attr_value(node, node_attr):
    if hasattr(node, "attributes") and isinstance(node.attributes, dict):
        value = node.attributes.get(node_attr)
        if isinstance(value, str):
            return value.strip()
        return value

    return None


def extract_pagination_details(page_html):
    pagination_elem = page_html.xpath('//*/script[@data-a-state=\'{"key":"scrollState"}\']/text()')
    if pagination_elem:
        pagination_details = ast.literal_eval(pagination_elem[0])
        return pagination_details
    return None


def get_external_image(link):
    logger.debug(f"Retrieving canonical image from external link {link}")

    external_image_session = requests.Session(impersonate="chrome")

    parser = etree.HTMLParser(encoding="utf-8", recover=True)

    external_r = external_image_session.get(link, headers={"Referer": "https://www.amazon.com/"})
    external_page = html.fromstring(external_r.content, parser=parser)

    og_image = external_page.xpath("//meta[@property='og:image']/@content")
    if og_image:
        return og_image[0]

    twitter_image = external_page.xpath("//meta[@name='twitter:image']/@content")
    if twitter_image:
        return twitter_image[0]

    link_image_src = external_page.xpath("//link[@rel='image_src']/@href")
    if link_image_src:
        return link_image_src[0]

    microdata_image = external_page.xpath("//*[@itemprop='image']/@content | //*[@itemprop='image']/@src")
    if microdata_image:
        return microdata_image[0]

    schema_image_json = external_page.xpath("//script[@type='application/ld+json']/text()")
    for schema_json in schema_image_json:
        try:
            schema_data = json.loads(schema_json)
            if isinstance(schema_data, dict) and "image" in schema_data:
                # In case 'image' is a list or a single string, return the first URL
                if isinstance(schema_data["image"], list):
                    return schema_data["image"][0]
                return schema_data["image"]
        except json.JSONDecodeError:
            continue  # Skip if not valid JSON

    logger.debug(f"No canonical image determined for {link}")
    return None


def get_pages_from_web(base_url, wishlist_url):
    parser = etree.HTMLParser(encoding="utf-8")
    wishlist_pages = []

    s = requests.Session(impersonate="chrome")
    logger.debug(f"Requesting {wishlist_url}")
    initial_request = s.get(wishlist_url)
    initial_page_html = html.fromstring(initial_request.content)

    captcha_element = initial_page_html.xpath("//*/form[@action='/errors/validateCaptcha']")
    if captcha_element:
        logger.debug("Captcha was hit. Attempting to solve...")
        initial_page_html = solve_captcha(s, base_url, initial_page_html, wishlist_url)

    wishlist_pages.append(initial_page_html)

    # Handle pagination
    pagination_details = extract_pagination_details(initial_page_html)

    while pagination_details and pagination_details["lastEvaluatedKey"]:
        next_page_url = f"{base_url}{pagination_details['showMoreUrl']}"
        sleep(3)  # Slightly prevent anti-bot measures
        logger.debug(f"Requesting paginated URL {next_page_url}")
        r = s.get(next_page_url)
        current_page = html.fromstring(r.content, parser=parser)
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


def solve_captcha(session, base_url, initial_page_html, wishlist_url, max_retries=3):
    captcha_link = initial_page_html.xpath(
        "//*/img[starts-with(@src,'https://images-na.ssl-images-amazon.com/captcha')]/@src"
    )
    hidden_value = initial_page_html.xpath("//*/input[@name='amzn']/@value")

    if not captcha_link or not hidden_value:
        raise Exception("Captcha elements not found on the page.")

    captcha_link = captcha_link[0]
    hidden_value = hidden_value[0]
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
                return html.fromstring(retry_page_response.content)
        else:
            logger.debug(f"Captcha solution attempt {attempt + 1} failed. Retrying...")

    raise Exception(f"Failed to solve captcha after {max_retries} attempts.")

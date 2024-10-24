# amazon-wishlist-exporter
amazon-wishlist-exporter.py - Scrapes Amazon wishlist data to JSON format

    usage: amazon_wishlist_exporter.py [-h] (-i ID | -u URL | -f HTML_FILE) [-t STORE_TLD] [-l STORE_LOCALE] [-p] [-d] [-s SORT_KEYS] [-c] [-y] [-o OUTPUT_FILE]
    
    options:
      -h, --help            show this help message and exit
      -i ID, --id ID        Amazon wishlist ID
      -u URL, --url URL     Amazon wishlist URL
      -f HTML_FILE, --html-file HTML_FILE
                            Amazon wishlist HTML file
      -t STORE_TLD, --store-tld STORE_TLD
                            Amazon store TLD
      -l STORE_LOCALE, --store-locale STORE_LOCALE, --locale STORE_LOCALE
                            Amazon store locale
      -p, --priority-is-localized
                            Return localized priority text instead of numeric value
      -d, --iso8601         Convert localized date strings to ISO 8601 format
      -s SORT_KEYS, --sort-keys SORT_KEYS
                            Sort key(s) for JSON output
      -c, --compact-json    Write compacted JSON
      -y, --force           Overwrite existing output file without asking
      -o OUTPUT_FILE, --output-file OUTPUT_FILE
                            Output JSON file

## Installation

Install with pip:

    pip install amazon-wishlist-exporter

[uv](https://docs.astral.sh/uv/) or [pipx](https://pipx.pypa.io/stable/) is recommended to install the package in a managed environment:

    uv tool install amazon-wishlist-exporter

For improved sorting of non-Latin or mixed scripts with the Unicode Collation Algorithm, install with the optional `icu` dependency:

    uv tool install amazon-wishlist-exporter[icu]

PyICU may need to be built separately: https://gitlab.pyicu.org/main/pyicu#installing-pyicu

Windows users can use pre-built wheels from here: https://github.com/cgohlke/pyicu-build/releases

Utilizing uv:

    uv tool install amazon-wishlist-exporter --python 3.11 --with https://github.com/cgohlke/pyicu-build/releases/download/v2.13/PyICU-2.13-cp311-cp311-win_amd64.whl

## Dependencies

* Python >= 3.11
* amazoncaptcha
* babel
* curl_cffi
* dateparser
* lxml
* price_parser
* PyICU (optional)

## Options

* `--id`: The ID of the wishlist, highlighted in bold in this example URL: `https://www.amazon.com/hz/wishlist/ls/` **XXXXXXXXXX** `/ref=nav_wishlist_lists_1`
* `--url`: Alternative to the above, allows whole wishlist URL as input - may need to be quoted
* `--html`: For HTML files generated via below instructions
* `--store-tld`: Required unless using `--url` - Any valid Amazon store TLD such as com, co.uk, de, etc.
* `--store-locale`: Optional unless using `--html` - Store locale such as en_US, en_GB, de_DE, etc. - not all stores support all locales. If not specified, the default locale for that store will be chosen.
* `--sort-keys`: Optional - A single key or comma separated list of key names to sort the wishlist items by. Example `priority,name` sorts first by priority value highest to lowest, then sorts by name
  * Numeric values (such as priority, rating) are sorted largest to smallest
  * String values (such as name, comment) are sorted using the Unicode Collation Algorithm and adjusted to the specified locale

## Limitations


### 403 Errors

Excessive scraping in a short time frame will cause Amazon to serve HTTP 403 errors to the session, but will clear on its own after some time.

### Private Wishlists and "Date Added" Field

This program is not capable of scraping private lists or authentication. Additionally, the "date added" field is only visible when you are authenticated.

To scrape these lists, you must use the bookmarklet provided in the below section, which will download an HTML file you can pass to the program with the `--html-file` argument.

#### How to generate HTML files from a wishlist

Using "Save As" in the browser will not create a usable HTML file for this program.

To work around this, I created a bookmarklet which you can save and then open on any wishlist page. It will continuously scroll to the bottom until the list is fully loaded, and then save the rendered DOM to an HTML file with a filename understood by this program.

Create a blank/dummy bookmark in your browser and replace the URL with this value:

    javascript:(function()%7Bif(window.location.host.startsWith(%22www.amazon.%22))var%20previousCount%3D-1%2CunchangedCount%3D0%2CcheckExist%3DsetInterval(function()%7Bvar%20e%3Ddocument.querySelectorAll(%22.g-item-sortable%22)%3Bif(document.getElementById(%22endOfListMarker%22)%7C%7CunchangedCount%3E%3D3)%7BclearInterval(checkExist)%3Blet%20t%3Ddocument.createElement(%22a%22)%2Cn%3Dnew%20Blob(%5Bdocument.getElementById(%22wishlist-page%22).outerHTML%5D%2C%7Btype%3A%22text%2Fhtml%22%7D)%3Bvar%20o%3Dwindow.location.host%2B%22_%22%2Bdocument.getElementById(%22listId%22).value%2B%22_%22%2Bopts.language%2B%22.html%22%3Bt.href%3DURL.createObjectURL(n)%2Ct.download%3Do%2Ct.click()%2CURL.revokeObjectURL(t.href)%7Delse%20e.length%3D%3D%3DpreviousCount%3FunchangedCount%2B%2B%3AunchangedCount%3D0%2CpreviousCount%3De.length%2C(last%3De%5Be.length-1%5D).scrollIntoView()%7D%2C2e3)%3Belse%20alert(%22This%20bookmarklet%20must%20be%20run%20on%20an%20Amazon%20site!%22)%3B%7D)()%3B

Alternatively, you can open a console using your browser's development tools, and then run the code that way:

```javascript
if(window.location.host.startsWith("www.amazon."))var previousCount=-1,unchangedCount=0,checkExist=setInterval(function(){var e=document.querySelectorAll(".g-item-sortable");if(document.getElementById("endOfListMarker")||unchangedCount>=3){clearInterval(checkExist);let t=document.createElement("a"),n=new Blob([document.getElementById("wishlist-page").outerHTML],{type:"text/html"});var o=window.location.host+"_"+document.getElementById("listId").value+"_"+opts.language+".html";t.href=URL.createObjectURL(n),t.download=o,t.click(),URL.revokeObjectURL(t.href)}else e.length===previousCount?unchangedCount++:unchangedCount=0,previousCount=e.length,(last=e[e.length-1]).scrollIntoView()},2e3);else alert("This bookmarklet must be run on an Amazon site!");
```

# Todo

* Logging
* Testing
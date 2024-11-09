import sys
from pathlib import Path

from amazon_wishlist_exporter.cli import cli


def generate_test_data(html_files):
    args = ["-s", "asin,name", "-y", "--debug", "--test"]

    for html_file in html_files:
        output_path = Path(html_file.parents[1] / "json_from_html" / html_file.name).with_suffix(".json")

        # Set up sys.argv to simulate CLI arguments
        sys.argv = ["cli.py", *args, "-f", str(html_file), "-o", str(output_path)]

        print(f"Generating JSON for {html_file}")

        cli()


if __name__ == "__main__":
    input_dir = Path("./testdata/html_playwright")
    input_files = list(input_dir.glob("*.html"))

    generate_test_data(input_files)

import sys
import json
from pathlib import Path
from io import StringIO

import pytest
from amazon_wishlist_exporter.cli import cli


def run_cli_on_html_file(html_file):
    args = ["-s", "asin,name", "-y", "--debug", "--test", "-f", str(html_file)]

    # Temporarily redirect stdout to capture the JSON output
    original_stdout = sys.stdout
    sys.stdout = StringIO()
    try:
        sys.argv = ["cli.py", *args]
        cli()  # This will print JSON to stdout
        json_output = sys.stdout.getvalue()
    finally:
        # Restore the original stdout
        sys.stdout = original_stdout

    return json.loads(json_output)


@pytest.mark.parametrize("html_file", list(Path("./testdata/html_playwright").glob("*.html")))
def test_generated_json_matches_truth(html_file):
    # Run the CLI on the HTML file and capture the JSON output
    generated_json = run_cli_on_html_file(html_file)

    # Load the original JSON file for comparison
    truth_json_path = Path(html_file.parents[1] / "json_from_html" / html_file.name).with_suffix(".json")
    with truth_json_path.open("r", encoding="utf-8") as truth_file:
        truth_json = json.load(truth_file)

    # Assert that the generated JSON matches the source-of-truth JSON
    assert generated_json == truth_json, f"Mismatch for {html_file.name}"

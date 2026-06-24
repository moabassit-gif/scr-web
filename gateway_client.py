from __future__ import annotations  # Enable modern type-hint behavior for forward references.

import argparse  # Build a command-line interface for the gateway client.
import json  # Format API responses as readable JSON.
import os  # Read environment variables such as GATEWAY_BASE_URL.
import sys  # Write error messages to stderr and return process exit codes.
from typing import Any  # Type arbitrary JSON-like values.
from urllib.parse import urlencode  # Safely encode query parameters into URLs.

import requests  # Send HTTP requests to the gateway API.


DEFAULT_PUBLIC_GATEWAY = "https://scr-web.your-radar.workers.dev"  # Public Cloudflare gateway URL.
DEFAULT_BASE_URL = os.getenv("GATEWAY_BASE_URL", DEFAULT_PUBLIC_GATEWAY)  # Prefer env URL, otherwise Cloudflare.


def request_json(base_url: str, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Call one gateway endpoint and return its JSON response."""  # Explain the helper purpose.
    url = f"{base_url.rstrip('/')}{path}"  # Join the base URL and endpoint path cleanly.
    response = requests.get(url, params=params or {}, timeout=60)  # Send a GET request with query params.
    response.raise_for_status()  # Raise an exception for HTTP 4xx/5xx responses.
    return response.json()  # Parse and return the gateway JSON response.


def print_json(data: Any) -> None:
    """Print JSON without escaping Arabic or other non-ASCII text."""  # Explain output formatting.
    print(json.dumps(data, ensure_ascii=False, indent=2))  # Pretty-print the response for humans.


def build_parser() -> argparse.ArgumentParser:
    """Create the command-line parser and all supported subcommands."""  # Explain parser setup.
    parser = argparse.ArgumentParser(description="Client for the SCR Web gateway API")  # Main CLI parser.
    parser.add_argument(  # Add a global option shared by every command.
        "--base-url",  # Allow callers to override the gateway URL.
        default=DEFAULT_BASE_URL,  # Use env var or Cloudflare URL by default.
        help=f"Gateway base URL. Default: GATEWAY_BASE_URL or {DEFAULT_PUBLIC_GATEWAY}",  # Help text.
    )

    subparsers = parser.add_subparsers(dest="command", required=True)  # Create required subcommands.

    links = subparsers.add_parser("links", help="Search and return links only")  # /links command.
    links.add_argument("query")  # Keyword to search for.
    links.add_argument("--limit", type=int, default=10)  # Number of results, from 1 to 10.
    links.add_argument("--country", default=None)  # Optional country code like eg, us, or sa.

    articles = subparsers.add_parser("articles", help="Search links and scrape article JSON")  # /articles command.
    articles.add_argument("query")  # Keyword to search for.
    articles.add_argument("--limit", type=int, default=10)  # Number of articles to request.
    articles.add_argument("--country", default=None)  # Optional country code for localized results.

    scrape = subparsers.add_parser("scrape-url", help="Scrape one article URL")  # /scrape-url command.
    scrape.add_argument("url")  # Full article URL to scrape.

    raw = subparsers.add_parser("serper-raw", help="Return raw Serper response")  # /serper-raw command.
    raw.add_argument("query")  # Keyword to send directly to Serper.
    raw.add_argument("--limit", type=int, default=10)  # Number of raw search results.
    raw.add_argument("--country", default=None)  # Optional country code for Serper gl parameter.

    subparsers.add_parser("usage", help="Show Serper key usage")  # /search-usage command.

    url = subparsers.add_parser("url", help="Print a gateway URL without calling it")  # URL builder command.
    url.add_argument("endpoint", choices=["links", "articles", "serper-raw"])  # Endpoint to build.
    url.add_argument("query")  # Keyword to include in the generated URL.
    url.add_argument("--limit", type=int, default=10)  # Result limit in the generated URL.
    url.add_argument("--country", default=None)  # Optional country code in the generated URL.

    return parser  # Return the configured parser to main().


def main() -> int:
    """Run the selected CLI command and return an exit code."""  # Explain entrypoint behavior.
    parser = build_parser()  # Build the CLI parser.
    args = parser.parse_args()  # Parse command-line arguments.
    base_url = args.base_url.rstrip("/")  # Normalize the base URL once.

    try:  # Convert gateway/network failures into clean CLI output.
        if args.command == "links":  # Handle the links command.
            data = request_json(  # Request /links from the gateway.
                base_url,  # Gateway base URL.
                "/links",  # Endpoint path.
                {"q": args.query, "limit": args.limit, "country": args.country},  # Query parameters.
            )
        elif args.command == "articles":  # Handle the articles command.
            data = request_json(  # Request /articles from the gateway.
                base_url,  # Gateway base URL.
                "/articles",  # Endpoint path.
                {"q": args.query, "limit": args.limit, "country": args.country},  # Query parameters.
            )
        elif args.command == "scrape-url":  # Handle the scrape-url command.
            data = request_json(base_url, "/scrape-url", {"url": args.url})  # Scrape the provided URL.
        elif args.command == "serper-raw":  # Handle the serper-raw command.
            data = request_json(  # Request raw Serper JSON through the gateway.
                base_url,  # Gateway base URL.
                "/serper-raw",  # Endpoint path.
                {"q": args.query, "limit": args.limit, "country": args.country},  # Query parameters.
            )
        elif args.command == "usage":  # Handle the usage command.
            data = request_json(base_url, "/search-usage")  # Request local key usage tracking.
        elif args.command == "url":  # Handle the URL builder command.
            params = {"q": args.query, "limit": args.limit}  # Start with required URL params.
            if args.country:  # Add country only when the caller provided it.
                params["country"] = args.country  # Store the country code in URL params.
            print(f"{base_url}/{args.endpoint}?{urlencode(params)}")  # Print the generated URL.
            return 0  # Exit successfully after printing the URL.
        else:  # This should not happen because argparse validates commands.
            parser.error("Unknown command")  # Show a standard argparse error.
            return 2  # Return a CLI usage error code.
    except requests.HTTPError as exc:  # Handle non-2xx responses from the gateway.
        print(f"Gateway returned an error: {exc.response.status_code}", file=sys.stderr)  # Show status code.
        try:  # Try to show the gateway JSON error body.
            print_json(exc.response.json())  # Print JSON error details when available.
        except ValueError:  # Fall back when the response body is not JSON.
            print(exc.response.text, file=sys.stderr)  # Print raw error text.
        return 1  # Return a general failure code.
    except requests.RequestException as exc:  # Handle network, timeout, and connection errors.
        print(f"Could not reach gateway: {exc}", file=sys.stderr)  # Show the connection error.
        return 1  # Return a general failure code.

    print_json(data)  # Print the successful JSON response.
    return 0  # Return success.


if __name__ == "__main__":  # Run main only when executed as a script.
    raise SystemExit(main())  # Convert main's return code into the process exit status.

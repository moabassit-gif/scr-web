from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any
from urllib.parse import urlencode

import requests


DEFAULT_BASE_URL = os.getenv("GATEWAY_BASE_URL", "http://127.0.0.1:8000")


def request_json(base_url: str, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    url = f"{base_url.rstrip('/')}{path}"
    response = requests.get(url, params=params or {}, timeout=60)
    response.raise_for_status()
    return response.json()


def print_json(data: Any) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Client for the SCR Web gateway API")
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help="Gateway base URL. Default: GATEWAY_BASE_URL or http://127.0.0.1:8000",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    links = subparsers.add_parser("links", help="Search and return links only")
    links.add_argument("query")
    links.add_argument("--limit", type=int, default=10)
    links.add_argument("--country", default=None)

    articles = subparsers.add_parser("articles", help="Search links and scrape article JSON")
    articles.add_argument("query")
    articles.add_argument("--limit", type=int, default=10)
    articles.add_argument("--country", default=None)

    scrape = subparsers.add_parser("scrape-url", help="Scrape one article URL")
    scrape.add_argument("url")

    raw = subparsers.add_parser("serper-raw", help="Return raw Serper response")
    raw.add_argument("query")
    raw.add_argument("--limit", type=int, default=10)
    raw.add_argument("--country", default=None)

    subparsers.add_parser("usage", help="Show Serper key usage")

    url = subparsers.add_parser("url", help="Print a gateway URL without calling it")
    url.add_argument("endpoint", choices=["links", "articles", "serper-raw"])
    url.add_argument("query")
    url.add_argument("--limit", type=int, default=10)
    url.add_argument("--country", default=None)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    base_url = args.base_url.rstrip("/")

    try:
        if args.command == "links":
            data = request_json(
                base_url,
                "/links",
                {"q": args.query, "limit": args.limit, "country": args.country},
            )
        elif args.command == "articles":
            data = request_json(
                base_url,
                "/articles",
                {"q": args.query, "limit": args.limit, "country": args.country},
            )
        elif args.command == "scrape-url":
            data = request_json(base_url, "/scrape-url", {"url": args.url})
        elif args.command == "serper-raw":
            data = request_json(
                base_url,
                "/serper-raw",
                {"q": args.query, "limit": args.limit, "country": args.country},
            )
        elif args.command == "usage":
            data = request_json(base_url, "/search-usage")
        elif args.command == "url":
            params = {"q": args.query, "limit": args.limit}
            if args.country:
                params["country"] = args.country
            print(f"{base_url}/{args.endpoint}?{urlencode(params)}")
            return 0
        else:
            parser.error("Unknown command")
            return 2
    except requests.HTTPError as exc:
        print(f"Gateway returned an error: {exc.response.status_code}", file=sys.stderr)
        try:
            print_json(exc.response.json())
        except ValueError:
            print(exc.response.text, file=sys.stderr)
        return 1
    except requests.RequestException as exc:
        print(f"Could not reach gateway: {exc}", file=sys.stderr)
        return 1

    print_json(data)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

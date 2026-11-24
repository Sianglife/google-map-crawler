"""Print a Maps URL; the default full URL demonstrates the offline path."""

import argparse
import sys

from google_map_crawler import CrawlerError, expand_short_url


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a Maps URL or expand a short link.")
    parser.add_argument("url", nargs="?", default="https://www.google.com/maps/search/?api=1&query=Taipei%20101")
    parser.add_argument("--timeout", type=float, default=30)
    parser.add_argument("--max-redirects", type=int, default=10)
    parser.add_argument("--max-retries", type=int, default=3)
    parser.add_argument("--no-browser", action="store_true", help="Use HTTP only.")
    args = parser.parse_args()
    try:
        result = expand_short_url(
            args.url, timeout=args.timeout, max_redirects=args.max_redirects,
            max_retries=args.max_retries, browser_fallback=not args.no_browser,
        )
    except CrawlerError as error:
        print(f"{type(error).__name__}: {error}", file=sys.stderr)
        return 2
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

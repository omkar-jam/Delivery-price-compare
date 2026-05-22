"""CLI: scrape any platform, compare multiple menus, export Excel."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from app.compare_menu import (
    compare_menus,
    load_mapping_csv,
    load_menu_csv,
    load_menus,
    load_pos_csv,
    load_uber_csv,
)
from app.export_excel import export_report
from scrapers.registry import detect_platform, list_platforms, save_menu_csv, scrape_url


def cmd_scrape(args: argparse.Namespace) -> int:
    url = args.url or os.environ.get("DELIVERY_STORE_URL", "").strip()
    if not url:
        print("Error: pass --url or set DELIVERY_STORE_URL", file=sys.stderr)
        return 1
    platform = args.platform or detect_platform(url)
    print(f"Scraping [{platform}] {url} ...")
    items = scrape_url(url, platform=args.platform, headless=not args.no_headless)
    if not items:
        print(
            "Warning: no menu items found. The site may have changed; try --platform generic.",
            file=sys.stderr,
        )
    path = save_menu_csv(items, args.output)
    print(f"Saved {len(items)} items to {path}")
    return 0 if items else 1


def cmd_platforms(_: argparse.Namespace) -> int:
    for row in list_platforms():
        print(f"{row['id']:12}  {row['name']:20}  {row['url_patterns']}")
    return 0


def _load_online_data(args: argparse.Namespace):
    if args.menus:
        return load_menus(menus_dir=args.menus)
    menu_paths = list(args.menu or [])
    if args.uber:
        menu_paths.append(args.uber)
    if menu_paths:
        return load_menus(menu_paths=menu_paths)
    raise ValueError("Provide --menu, --menus, or legacy --uber")


def cmd_compare(args: argparse.Namespace) -> int:
    online_df = _load_online_data(args)
    pos_df = load_pos_csv(args.pos)
    mapping = load_mapping_csv(args.mapping)
    comparison, unmatched_online, unmatched_pos = compare_menus(online_df, pos_df, mapping)
    menus_raw = online_df.drop(columns=["online_name_norm"], errors="ignore")
    export_report(
        args.output,
        comparison,
        unmatched_online,
        unmatched_pos,
        menus_raw,
        pos_df.drop(columns=["pos_name_norm"], errors="ignore"),
    )
    matched = (comparison["pos_id"].astype(str).str.len() > 0).sum()
    print(f"Report written to {args.output}")
    print(f"Online items: {len(online_df)} | Matched: {matched}")
    if "platform" in comparison.columns:
        print(comparison.groupby("platform").size().to_string())
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    url = args.url or os.environ.get("DELIVERY_STORE_URL", "").strip()
    if not url:
        print("Error: pass --url or set DELIVERY_STORE_URL", file=sys.stderr)
        return 1
    cache = Path(args.menu_cache or "data/scraped_menu.csv")
    items = scrape_url(url, platform=args.platform, headless=not args.no_headless)
    save_menu_csv(items, cache)
    args.menu = [str(cache)]
    return cmd_compare(args)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="app",
        description="Scrape delivery platform menus and compare prices with POS exports.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    scrape = sub.add_parser("scrape", help="Scrape a delivery platform store menu to CSV")
    scrape.add_argument("--url", help="Store URL (or DELIVERY_STORE_URL)")
    scrape.add_argument("--platform", help="Force platform id (see: platforms)")
    scrape.add_argument("--output", default="menu.csv", help="Output CSV path")
    scrape.add_argument("--no-headless", action="store_true", help="Show browser window")
    scrape.set_defaults(func=cmd_scrape)

    platforms = sub.add_parser("platforms", help="List supported delivery platforms")
    platforms.set_defaults(func=cmd_platforms)

    compare = sub.add_parser("compare", help="Compare menu CSV(s) with POS CSV")
    compare.add_argument("--pos", required=True, help="POS export CSV")
    compare.add_argument(
        "--menu",
        action="append",
        default=[],
        help="Menu CSV (repeat for multiple platforms)",
    )
    compare.add_argument("--menus", help="Directory of menu CSV files")
    compare.add_argument("--uber", help="Legacy: single Uber menu CSV")
    compare.add_argument("--mapping", help="Optional manual mapping CSV")
    compare.add_argument("--output", default="report.xlsx", help="Excel report path")
    compare.set_defaults(func=cmd_compare)

    run = sub.add_parser("run", help="Scrape one URL then compare with POS")
    run.add_argument("--url", help="Store URL")
    run.add_argument("--platform", help="Force platform id")
    run.add_argument("--pos", required=True, help="POS export CSV")
    run.add_argument("--menu", action="append", default=[])
    run.add_argument("--menus", help="Directory of extra menu CSVs to include")
    run.add_argument("--mapping", help="Optional mapping CSV")
    run.add_argument("--output", default="report.xlsx")
    run.add_argument("--menu-cache", help="Where to save scraped menu CSV")
    run.add_argument("--no-headless", action="store_true")
    run.set_defaults(func=cmd_run)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

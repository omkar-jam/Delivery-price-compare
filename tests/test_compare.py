"""Unit tests for menu comparison (no live scraping)."""

from pathlib import Path

import pandas as pd
import pytest

from app.compare_menu import compare_menus, load_mapping_csv, load_menu_csv, load_menus, load_pos_csv, load_uber_csv
from app.export_excel import export_report
from app.utils import normalize_name, parse_price

SAMPLES = Path(__file__).resolve().parent.parent / "samples"
MENUS = SAMPLES / "menus"


def test_normalize_name_strips_punctuation():
    assert normalize_name("Fish & Chips!") == "fish chips"


def test_parse_price_gbp_and_usd():
    assert parse_price("£9.50") == 9.50
    assert parse_price("$12.99") == 12.99
    assert parse_price("€8,50") == 8.50


def test_load_pos_flexible_columns():
    df = load_pos_csv(SAMPLES / "pos_export.csv")
    assert "pos_name" in df.columns
    assert len(df) == 15


def test_fuzzy_matching_single_platform():
    online_df = load_menu_csv(MENUS / "uber_eats.csv")
    pos_df = load_pos_csv(SAMPLES / "pos_export.csv")
    mapping = load_mapping_csv(SAMPLES / "mapping.csv")
    comparison, unmatched_online, unmatched_pos = compare_menus(online_df, pos_df, mapping)

    assert len(comparison) == len(online_df)
    assert "platform" in comparison.columns
    assert comparison["platform"].iloc[0] == "uber_eats"

    mapped = comparison[comparison["online_name"] == "Pepperoni Feast"].iloc[0]
    assert mapped["pos_id"] == "P002"
    assert mapped["match_score"] == 100.0

    margherita = comparison[comparison["online_name"] == "Margherita Pizza"].iloc[0]
    assert margherita["pos_name"] == "Margherita Pizza"
    assert margherita["diff"] == pytest.approx(0.49, abs=0.01)

    assert "Uber Exclusive Wings" in unmatched_online["online_name"].values


def test_multi_platform_compare():
    online_df = load_menus(menus_dir=MENUS)
    pos_df = load_pos_csv(SAMPLES / "pos_export.csv")
    comparison, _, _ = compare_menus(online_df, pos_df, {})
    platforms = set(comparison["platform"].unique())
    assert platforms >= {"uber_eats", "deliveroo", "doordash"}
    assert len(comparison) == len(online_df)


def test_legacy_uber_csv_loader():
    df = load_uber_csv(SAMPLES / "uber_menu_sample.csv")
    assert "uber_name" in df.columns


def test_excel_export(tmp_path):
    online_df = load_menus(menus_dir=MENUS)
    pos_df = load_pos_csv(SAMPLES / "pos_export.csv")
    comparison, unmatched_online, unmatched_pos = compare_menus(online_df, pos_df, {})
    out = tmp_path / "report.xlsx"
    export_report(
        out,
        comparison=comparison,
        unmatched_online=unmatched_online,
        unmatched_pos=unmatched_pos,
        menus_raw=online_df.drop(columns=["online_name_norm"], errors="ignore"),
        pos_raw=pos_df.drop(columns=["pos_name_norm"], errors="ignore"),
    )
    assert out.exists()
    sheets = pd.ExcelFile(out).sheet_names
    assert sheets == [
        "Summary",
        "Comparison",
        "Unmatched_Uber",
        "Unmatched_POS",
        "Uber_Raw",
        "POS_Raw",
    ]
    comp = pd.read_excel(out, sheet_name="Comparison")
    assert "platform" in comp.columns

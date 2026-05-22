"""Fuzzy matching between delivery platform menus and POS export."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from rapidfuzz import fuzz, process

from app.category_match import (
    combined_match_score,
    infer_product_families,
    strict_name_family_ok,
)
from app.utils import detect_column, normalize_name, parse_price

MATCH_THRESHOLD = 72
CATEGORY_AWARE_THRESHOLD = 78


def load_pos_csv(path: str | Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    id_col = detect_column(list(df.columns), ["pos_id", "id", "sku", "item_id", "code"])
    name_col = detect_column(list(df.columns), ["name", "item_name", "product", "description"])
    price_col = detect_column(list(df.columns), ["price", "unit_price", "sell_price", "amount"])
    category_col = detect_column(
        list(df.columns), ["category_name", "category", "section", "menu_category"]
    )
    if not name_col:
        raise ValueError(f"Could not detect name column in POS CSV: {list(df.columns)}")
    out = pd.DataFrame()
    out["pos_id"] = df[id_col] if id_col else range(1, len(df) + 1)
    out["pos_name"] = df[name_col].astype(str)
    out["pos_price"] = df[price_col].apply(parse_price) if price_col else None
    out["pos_category"] = (
        df[category_col].fillna("").astype(str) if category_col else ""
    )
    out["pos_name_norm"] = out["pos_name"].map(normalize_name)
    out["pos_family"] = out.apply(
        lambda r: ",".join(sorted(infer_product_families(r["pos_name"], r["pos_category"]))),
        axis=1,
    )
    return out


def load_menu_csv(path: str | Path, platform: str | None = None) -> pd.DataFrame:
    """Load a scraped menu CSV (any delivery platform)."""
    df = pd.read_csv(path)
    name_col = detect_column(list(df.columns), ["name", "item_name", "title", "online_name"])
    price_col = detect_column(list(df.columns), ["price", "online_price", "unit_price"])
    platform_col = detect_column(list(df.columns), ["platform"])
    category_col = detect_column(list(df.columns), ["category", "section"])

    if not name_col:
        raise ValueError(f"Could not detect name column in menu CSV: {list(df.columns)}")

    out = pd.DataFrame()
    if platform_col:
        out["platform"] = df[platform_col].astype(str)
    elif platform:
        out["platform"] = platform
    else:
        stem = Path(path).stem.lower()
        for pid in ("uber_eats", "doordash", "deliveroo", "grubhub", "just_eat"):
            if pid.replace("_", "") in stem.replace("_", "").replace("-", ""):
                out["platform"] = pid
                break
        else:
            out["platform"] = "unknown"

    out["online_name"] = df[name_col].astype(str)
    out["online_price"] = df[price_col].apply(parse_price) if price_col else None
    if category_col:
        out["category"] = df[category_col].fillna("").astype(str)
    else:
        out["category"] = ""
    out["online_name_norm"] = out["online_name"].map(normalize_name)
    out["online_family"] = out.apply(
        lambda r: ",".join(sorted(infer_product_families(r["online_name"], r.get("category", "")))),
        axis=1,
    )
    out["source_file"] = str(Path(path).name)
    return out


def load_uber_csv(path: str | Path) -> pd.DataFrame:
    """Backward-compatible alias; maps uber_* columns for legacy tests."""
    df = load_menu_csv(path, platform="uber_eats")
    out = df.rename(
        columns={
            "online_name": "uber_name",
            "online_price": "uber_price",
            "online_name_norm": "uber_name_norm",
        }
    )
    return out


def load_menus(
    menu_paths: list[str | Path] | None = None,
    menus_dir: str | Path | None = None,
) -> pd.DataFrame:
    """Load and concatenate multiple menu CSVs."""
    paths: list[Path] = []
    if menu_paths:
        paths.extend(Path(p) for p in menu_paths)
    if menus_dir:
        paths.extend(sorted(Path(menus_dir).glob("*.csv")))
    if not paths:
        raise ValueError("Provide --menu paths and/or --menus directory.")

    frames = [load_menu_csv(p) for p in paths]
    return pd.concat(frames, ignore_index=True)


def load_mapping_csv(path: str | Path | None) -> dict[str, str]:
    if not path or not Path(path).exists():
        return {}
    df = pd.read_csv(path)
    online_col = detect_column(
        list(df.columns), ["online_name", "uber_name", "uber", "menu_name", "name"]
    )
    pos_col = detect_column(list(df.columns), ["pos_id", "id", "sku"])
    if not online_col or not pos_col:
        raise ValueError(
            f"mapping.csv needs online_name and pos_id columns; got {list(df.columns)}"
        )
    return {
        str(row[online_col]).strip(): str(row[pos_col]).strip()
        for _, row in df.iterrows()
        if str(row[online_col]).strip()
    }


def suggest_action(
    diff: float | None,
    diff_pct: float | None,
    matched: bool,
    *,
    category_ok: bool = True,
    match_score: float = 0.0,
) -> str:
    if not matched:
        return "review_unmatched"
    if not category_ok:
        return "review_category_mismatch"
    if match_score < CATEGORY_AWARE_THRESHOLD:
        return "review_low_confidence"
    if diff is None:
        return "review_missing_price"
    if abs(diff) < 0.01:
        return "ok"
    if diff > 0:
        return "lower_online_or_raise_pos"
    return "raise_online_or_lower_pos"


def _find_best_pos_match(
    online_name: str,
    online_category: str,
    online_norm: str,
    pos_df: pd.DataFrame,
    pos_names: list[str],
    threshold: int,
) -> tuple[pd.Series | None, float, bool]:
    """Pick best POS row using category-aware scoring (top fuzzy candidates first)."""
    candidates = process.extract(
        online_norm,
        pos_names,
        scorer=fuzz.token_sort_ratio,
        limit=25,
    )
    if not candidates:
        return None, 0.0, True

    best_row = None
    best_score = 0.0
    best_category_ok = True

    for matched_norm, _name_score, _ in candidates:
        idx = pos_names.index(matched_norm)
        pos_row = pos_df.iloc[idx]
        pos_name = str(pos_row["pos_name"])
        pos_cat = str(pos_row.get("pos_category", ""))
        score = combined_match_score(online_name, online_category, pos_name, pos_cat)
        if score < threshold:
            continue
        cat_ok = strict_name_family_ok(online_name, online_category, pos_name)
        if score > best_score or (score == best_score and cat_ok and not best_category_ok):
            best_score = score
            best_row = pos_row
            best_category_ok = cat_ok

    if best_row is not None:
        return best_row, best_score, best_category_ok
    return None, 0.0, False


def compare_menus(
    online_df: pd.DataFrame,
    pos_df: pd.DataFrame,
    mapping: dict[str, str] | None = None,
    threshold: int = MATCH_THRESHOLD,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Compare delivery menu(s) with POS.

    Accepts load_menu_csv output (online_*) or legacy load_uber_csv (uber_*).
    """
    mapping = mapping or {}
    if "uber_name" in online_df.columns and "online_name" not in online_df.columns:
        online_df = online_df.rename(
            columns={
                "uber_name": "online_name",
                "uber_price": "online_price",
                "uber_name_norm": "online_name_norm",
            }
        )
    if "platform" not in online_df.columns:
        online_df = online_df.copy()
        online_df["platform"] = "unknown"

    pos_by_id = pos_df.set_index(pos_df["pos_id"].astype(str))
    pos_names = pos_df["pos_name_norm"].tolist()
    pos_name_to_idx = {n: i for i, n in enumerate(pos_names)}

    rows: list[dict] = []
    matched_pos_ids: set[str] = set()

    for _, item in online_df.iterrows():
        online_name = item["online_name"]
        online_norm = item["online_name_norm"]
        platform = item.get("platform", "unknown")
        pos_row = None
        score = 0.0

        if online_name in mapping:
            pid = str(mapping[online_name])
            if pid in pos_by_id.index:
                pos_row = pos_by_id.loc[pid]
                score = 100.0
        if pos_row is None and online_norm in pos_name_to_idx:
            idx = pos_name_to_idx[online_norm]
            pos_row = pos_df.iloc[idx]
            score = 100.0
        category_ok = True
        if pos_row is None and pos_names:
            pos_row, score, category_ok = _find_best_pos_match(
                online_name,
                str(item.get("category", "")),
                online_norm,
                pos_df,
                pos_names,
                threshold,
            )

        if pos_row is not None:
            matched_pos_ids.add(str(pos_row["pos_id"]))
            online_price = item.get("online_price")
            pos_price = pos_row.get("pos_price")
            diff = None
            diff_pct = None
            if online_price is not None and pos_price is not None:
                diff = float(online_price) - float(pos_price)
                if float(pos_price) != 0:
                    diff_pct = (diff / float(pos_price)) * 100.0
            rows.append(
                {
                    "platform": platform,
                    "online_name": online_name,
                    "online_category": item.get("category", ""),
                    "online_family": item.get("online_family", ""),
                    "pos_name": pos_row["pos_name"],
                    "pos_category": pos_row.get("pos_category", ""),
                    "pos_family": pos_row.get("pos_family", ""),
                    "pos_id": pos_row["pos_id"],
                    "online_price": online_price,
                    "pos_price": pos_price,
                    "diff": diff,
                    "diff_pct": diff_pct,
                    "match_score": score,
                    "category_match_ok": category_ok,
                    "action": suggest_action(
                        diff, diff_pct, True, category_ok=category_ok, match_score=score
                    ),
                }
            )
        else:
            rows.append(
                {
                    "platform": platform,
                    "online_name": online_name,
                    "pos_name": "",
                    "pos_id": "",
                    "online_price": item.get("online_price"),
                    "pos_price": None,
                    "diff": None,
                    "diff_pct": None,
                    "match_score": 0.0,
                    "action": "review_unmatched_online",
                    "online_category": item.get("category", ""),
                    "online_family": item.get("online_family", ""),
                }
            )

    comparison = pd.DataFrame(rows)
    unmatched_online = comparison[comparison["pos_id"].astype(str).str.len() == 0].copy()
    unmatched_pos = pos_df[~pos_df["pos_id"].astype(str).isin(matched_pos_ids)].copy()
    return comparison, unmatched_online, unmatched_pos

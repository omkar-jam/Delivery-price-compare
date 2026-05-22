"""
Menu Price Comparator — web UI.

Run locally:  ./run.sh   or   streamlit run app_streamlit.py
Run hosted:   docker build -t menu-comparator . && docker run -p 8501:8501 menu-comparator
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

from app.compare_menu import compare_menus, load_mapping_csv, load_menu_csv, load_menus, load_pos_csv
from app.export_excel import export_report
from scrapers.registry import detect_platform, list_platforms, save_menu_csv, scrape_url

ROOT = Path(__file__).resolve().parent
SAMPLES = ROOT / "samples"

# Hosted Streamlit Cloud cannot run Playwright browsers without a custom image.
HOSTED_COMPARE_ONLY = bool(
    os.environ.get("STREAMLIT_SERVER_HEADLESS")
    and not Path("/ms-playwright").exists()
    and not os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
)

st.set_page_config(
    page_title="Menu Price Comparator",
    page_icon="🍽️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
<style>
    .block-container { padding-top: 1.5rem; max-width: 1100px; }
    .hero {
        background: linear-gradient(135deg, #06C16722 0%, #1A1F2E 100%);
        border: 1px solid #06C16744;
        border-radius: 12px;
        padding: 1.5rem 1.75rem;
        margin-bottom: 1.5rem;
    }
    .hero h1 { margin: 0; font-size: 1.75rem; }
    .hero p { margin: 0.5rem 0 0; color: #B0B8C4; }
    .step-badge {
        display: inline-block;
        background: #06C167;
        color: #0E1117;
        font-weight: 700;
        border-radius: 999px;
        padding: 0.15rem 0.65rem;
        font-size: 0.8rem;
        margin-right: 0.5rem;
    }
    div[data-testid="stMetric"] {
        background: #1A1F2E;
        border: 1px solid #2A3142;
        border-radius: 10px;
        padding: 0.75rem;
    }
</style>
""",
    unsafe_allow_html=True,
)


def init_session() -> None:
    defaults = {
        "menu_df": None,
        "comparison": None,
        "unmatched_online": None,
        "unmatched_pos": None,
        "pos_df": None,
        "report_bytes": None,
        "menu_csv_bytes": None,
        "last_url": "",
        "last_platform": "",
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


def run_scrape(url: str, *, headless: bool) -> pd.DataFrame:
    platform = detect_platform(url)
    progress = st.progress(0, text="Starting browser…")
    try:
        progress.progress(15, text=f"Opening {platform.replace('_', ' ').title()} menu…")
        items = scrape_url(url, platform=platform, headless=headless)
        progress.progress(85, text="Parsing menu items…")
        if not items:
            st.warning(
                "No items found. Try **Show browser** in the sidebar, accept cookies manually, "
                "or upload a menu CSV you exported earlier."
            )
            return pd.DataFrame()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "menu.csv"
            save_menu_csv(items, path)
            df = load_menu_csv(path, platform=platform)
        progress.progress(100, text=f"Done — {len(df)} items scraped")
        st.session_state.last_url = url
        st.session_state.last_platform = platform
        return df
    finally:
        progress.empty()


def run_compare(menu_df: pd.DataFrame, pos_bytes: bytes, mapping_bytes: bytes | None) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        pos_path = tmp_path / "pos.csv"
        pos_path.write_bytes(pos_bytes)
        pos_df = load_pos_csv(pos_path)

        mapping: dict[str, str] = {}
        if mapping_bytes:
            mp = tmp_path / "mapping.csv"
            mp.write_bytes(mapping_bytes)
            mapping = load_mapping_csv(mp)

        comparison, unmatched_online, unmatched_pos = compare_menus(menu_df, pos_df, mapping)
        report_path = tmp_path / "report.xlsx"
        export_report(
            report_path,
            comparison=comparison,
            unmatched_online=unmatched_online,
            unmatched_pos=unmatched_pos,
            menus_raw=menu_df.drop(columns=["online_name_norm"], errors="ignore"),
            pos_raw=pos_df.drop(columns=["pos_name_norm"], errors="ignore"),
        )

        st.session_state.menu_df = menu_df
        st.session_state.pos_df = pos_df
        st.session_state.comparison = comparison
        st.session_state.unmatched_online = unmatched_online
        st.session_state.unmatched_pos = unmatched_pos
        st.session_state.report_bytes = report_path.read_bytes()

        menu_csv_path = tmp_path / "menu_export.csv"
        menu_df.drop(columns=["online_name_norm"], errors="ignore").to_csv(
            menu_csv_path, index=False
        )
        st.session_state.menu_csv_bytes = menu_csv_path.read_bytes()


def render_results() -> None:
    comparison = st.session_state.comparison
    if comparison is None:
        return

    st.divider()
    st.subheader("Results")

    matched = len(comparison) - len(st.session_state.unmatched_online)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Menu items", len(st.session_state.menu_df))
    c2.metric("Matched to POS", matched)
    c3.metric("Unmatched online", len(st.session_state.unmatched_online))
    c4.metric("Unmatched POS", len(st.session_state.unmatched_pos))

    dl1, dl2 = st.columns(2)
    with dl1:
        st.download_button(
            "📥 Download Excel report",
            data=st.session_state.report_bytes,
            file_name="menu_pos_report.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary",
            use_container_width=True,
        )
    with dl2:
        if st.session_state.menu_csv_bytes:
            st.download_button(
                "📥 Download scraped menu CSV",
                data=st.session_state.menu_csv_bytes,
                file_name="scraped_menu.csv",
                mime="text/csv",
                use_container_width=True,
            )

    tab1, tab2, tab3, tab4 = st.tabs(
        ["Comparison", "Unmatched online", "Unmatched POS", "Full menu"]
    )
    with tab1:
        display = comparison.copy()
        for col in ("online_price", "pos_price", "diff"):
            if col in display.columns:
                display[col] = pd.to_numeric(display[col], errors="coerce").map(
                    lambda x: f"£{x:.2f}" if pd.notna(x) else "—"
                )
        if "diff_pct" in display.columns:
            display["diff_pct"] = pd.to_numeric(display["diff_pct"], errors="coerce").map(
                lambda x: f"{x:.1f}%" if pd.notna(x) else "—"
            )
        st.dataframe(display, use_container_width=True, height=420)
    with tab2:
        st.dataframe(st.session_state.unmatched_online, use_container_width=True, height=360)
    with tab3:
        st.dataframe(st.session_state.unmatched_pos, use_container_width=True, height=360)
    with tab4:
        st.dataframe(st.session_state.menu_df, use_container_width=True, height=420)


init_session()

# --- Sidebar ---
with st.sidebar:
    st.markdown("### Settings")
    headless = st.toggle("Headless browser", value=True, help="Turn off to watch scraping (local only)")
    show_browser = st.checkbox("Show browser window", value=False, help="Requires local run; unchecks headless")
    if show_browser:
        headless = False

    st.markdown("---")
    st.markdown("### Supported platforms")
    for row in list_platforms():
        if row["id"] != "generic":
            st.caption(f"**{row['name']}**")

    st.markdown("---")
    with st.expander("Run locally"):
        st.code("./run.sh", language="bash")
        st.caption("Or: `streamlit run app_streamlit.py`")

    with st.expander("Host on a server"):
        st.markdown(
            "Use the included **Dockerfile** (Playwright + Streamlit):\n"
            "```bash\ndocker build -t menu-comparator .\n"
            "docker run -p 8501:8501 menu-comparator\n```"
        )

    if HOSTED_COMPARE_ONLY:
        st.warning("Live scrape needs Docker/self-host. Upload a menu CSV or use samples.")

# --- Hero ---
st.markdown(
    """
<div class="hero">
  <h1>🍽️ Menu Price Comparator</h1>
  <p>Paste your delivery menu URL, upload your POS export, and download an Excel price comparison in minutes.</p>
</div>
""",
    unsafe_allow_html=True,
)

# --- Main form ---
col_main, col_help = st.columns([2, 1])

with col_main:
    st.markdown('<span class="step-badge">1</span> **Store URL**', unsafe_allow_html=True)
    store_url = st.text_input(
        "Delivery platform store link",
        placeholder="https://www.ubereats.com/gb/store/your-restaurant/...",
        label_visibility="collapsed",
    )
    if store_url.strip():
        plat = detect_platform(store_url.strip())
        st.caption(f"Detected platform: **{plat.replace('_', ' ').title()}**")

    st.markdown('<span class="step-badge">2</span> **POS export**', unsafe_allow_html=True)
    pos_file = st.file_uploader(
        "Upload CSV from your till / POS (pos_id, name, price)",
        type=["csv"],
        label_visibility="collapsed",
    )

    mapping_file = None
    with st.expander("Optional: manual name mapping"):
        mapping_file = st.file_uploader(
            "mapping.csv — when item names do not match (online_name, pos_id)",
            type=["csv"],
        )

    st.markdown('<span class="step-badge">3</span> **Run**', unsafe_allow_html=True)
    use_sample = st.checkbox("Demo with sample data (no live scrape)", value=False)

    btn_col1, btn_col2 = st.columns(2)
    full_run = btn_col1.button("Scrape & compare", type="primary", use_container_width=True)
    scrape_only = btn_col2.button("Scrape menu only", use_container_width=True)

with col_help:
    st.info(
        "**How it works**\n\n"
        "1. Paste your Uber Eats / Deliveroo / DoorDash store URL\n"
        "2. Upload a CSV export from your POS\n"
        "3. Get an Excel file with price differences and suggested actions\n\n"
        "First scrape may take 1–2 minutes while all menu categories load."
    )
    st.download_button(
        "Download sample POS CSV",
        data=(SAMPLES / "pos_export.csv").read_bytes(),
        file_name="pos_export_sample.csv",
        mime="text/csv",
        use_container_width=True,
    )

# --- Actions ---
if full_run or scrape_only:
    if use_sample:
        menu_df = load_menu_csv(SAMPLES / "menus" / "uber_eats.csv", platform="uber_eats")
        st.session_state.menu_df = menu_df
        st.success(f"Loaded {len(menu_df)} sample Uber Eats items")
        if full_run:
            if pos_file is None:
                pos_file_bytes = (SAMPLES / "pos_export.csv").read_bytes()
            else:
                pos_file_bytes = pos_file.getvalue()
            mapping_bytes = mapping_file.getvalue() if mapping_file else (SAMPLES / "mapping.csv").read_bytes()
            with st.spinner("Comparing prices…"):
                run_compare(menu_df, pos_file_bytes, mapping_bytes)
            st.success("Comparison complete")
            render_results()
        else:
            st.dataframe(menu_df, use_container_width=True)
    else:
        url = store_url.strip()
        if not url:
            st.error("Paste a store URL first.")
        elif full_run and pos_file is None:
            st.error("Upload your POS CSV to run a comparison.")
        elif HOSTED_COMPARE_ONLY:
            st.error(
                "Live scraping is not available on this host. Run locally with `./run.sh`, "
                "deploy the Docker image, or use **Already have a menu CSV?** below."
            )
        else:
            try:
                with st.spinner("Scraping menu — scrolling categories, please wait…"):
                    menu_df = run_scrape(url, headless=headless)
                if menu_df.empty:
                    st.stop()
                st.session_state.menu_df = menu_df
                st.success(f"Scraped **{len(menu_df)}** menu items")

                if scrape_only:
                    csv_bytes = menu_df.to_csv(index=False).encode()
                    st.download_button(
                        "Download menu CSV",
                        data=csv_bytes,
                        file_name="menu.csv",
                        mime="text/csv",
                        type="primary",
                    )
                    st.dataframe(menu_df, use_container_width=True, height=400)
                else:
                    with st.spinner("Matching items and building Excel report…"):
                        run_compare(
                            menu_df,
                            pos_file.getvalue(),
                            mapping_file.getvalue() if mapping_file else None,
                        )
                    st.success("Done — download your report below")
                    render_results()
            except Exception as exc:
                st.error(f"Scrape failed: {exc}")
                st.markdown(
                    "**Tips:** Run locally with `./run.sh`, enable **Show browser window**, "
                    "accept cookie popups, then try again. Ensure Playwright is installed: "
                    "`playwright install chromium`"
                )

# Show previous results if user navigates without re-running
if not (full_run or scrape_only) and st.session_state.comparison is not None:
    render_results()

# Optional: upload existing menus without scrape
with st.expander("Already have a menu CSV? Compare without scraping"):
    existing_menus = st.file_uploader("Menu CSV file(s)", type=["csv"], accept_multiple_files=True)
    pos_file2 = st.file_uploader("POS CSV", type=["csv"], key="pos_existing")
    if st.button("Compare uploaded files", key="compare_uploaded"):
        if not existing_menus or pos_file2 is None:
            st.error("Upload at least one menu CSV and a POS CSV.")
        else:
            with tempfile.TemporaryDirectory() as tmp:
                paths = []
                for i, f in enumerate(existing_menus):
                    p = Path(tmp) / f"menu_{i}.csv"
                    p.write_bytes(f.getvalue())
                    paths.append(p)
                menu_df = load_menus(menu_paths=paths)
                mapping_bytes = mapping_file.getvalue() if mapping_file else None
                with st.spinner("Comparing…"):
                    run_compare(menu_df, pos_file2.getvalue(), mapping_bytes)
            st.success("Comparison complete")
            render_results()

st.caption(
    "For stores you own or manage only. Scraping may break if platforms change their sites. "
    "See README for CLI usage and Docker deployment."
)

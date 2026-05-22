# Menu Price Comparator

Scrape restaurant menus from multiple delivery platforms, compare item prices against your POS export, and generate an Excel report to help adjust online pricing.

## Supported platforms

| Platform ID | Name | URL patterns (auto-detected) |
|-------------|------|------------------------------|
| `uber_eats` | Uber Eats | `ubereats.com`, `uber.com/eats` |
| `doordash` | DoorDash | `doordash.com`, `drd.sh` |
| `deliveroo` | Deliveroo | `deliveroo.co.uk`, `deliveroo.com` |
| `grubhub` | Grubhub | `grubhub.com`, `seamless.com` |
| `just_eat` | Just Eat | `just-eat.co.uk`, `just-eat.com` |
| `generic` | Generic DOM fallback | Any other menu URL |

List platforms from the CLI:

```bash
python -m app platforms
```

## Setup

```bash
cd ~/Projects/uber-menu-price-comparator
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

## Quick start (sample data, no live scrape)

```bash
python -m app compare \
  --pos samples/pos_export.csv \
  --menus samples/menus \
  --mapping samples/mapping.csv \
  --output samples/report.xlsx
```

Open `samples/report.xlsx`. The **Comparison** sheet includes a `platform` column for each delivery menu row.

## CLI usage

### Scrape a store menu

```bash
python -m app scrape --url "https://www.ubereats.com/gb/store/..." --output uber.csv
python -m app scrape --url "https://www.deliveroo.co.uk/menu/..." --platform deliveroo --output deliveroo.csv
```

Uber Eats menus load lazily: the scraper scrolls the full page, clicks each category tab in the sidebar, and merges all JSON + DOM data. A full menu may take 1–2 minutes. Use `--no-headless` to watch the browser if items are missing.

Set `DELIVERY_STORE_URL` instead of `--url` if you prefer an environment variable.

### Compare one or more menu CSVs with POS

```bash
python -m app compare --pos pos_export.csv --menu uber.csv --menu deliveroo.csv --output report.xlsx
python -m app compare --pos pos_export.csv --menus ./scraped_menus/ --output report.xlsx
```

### Scrape then compare

```bash
python -m app run --url "https://www.doordash.com/store/..." --pos pos_export.csv --output report.xlsx
```

## POS export format

Your POS CSV should include columns detectable as:

- **ID**: `pos_id`, `id`, `sku`, `item_id`
- **Name**: `name`, `item_name`, `product`, `description`
- **Price**: `price`, `unit_price`, `sell_price`, `amount`

See `samples/pos_export.csv`.

## Manual mapping

Optional `mapping.csv` overrides fuzzy matching:

```csv
online_name,pos_id
Pepperoni Feast,P002
```

## Scraped menu CSV format

Columns written by the scraper:

| Column | Description |
|--------|-------------|
| `name` | Item name |
| `price` | Numeric price (£, $, € supported) |
| `category` | Menu section if found |
| `platform` | Platform id |
| `scraped_at` | UTC timestamp |
| `source_url` | Store URL scraped |

## Excel report sheets

| Sheet | Contents |
|-------|----------|
| Comparison | Matched rows with `platform`, prices, diff, suggested action |
| Unmatched_Online | Delivery items with no POS match |
| Unmatched_POS | POS items not on any delivery menu |
| Menus_Raw | Combined scraped/uploaded menus |
| POS_Raw | Normalized POS data |

## Web UI (recommended)

Paste a store URL, upload your POS CSV, and download the Excel report — no terminal commands needed.

### Local

```bash
./run.sh
```

Opens **http://localhost:8501**. First run installs dependencies and Playwright Chromium automatically.

Or manually:

```bash
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
streamlit run app_streamlit.py
```

### Hosted (Docker)

Deploy on any server with Docker (Railway, Render, Fly.io, VPS):

```bash
docker compose up --build
```

Or:

```bash
docker build -t menu-comparator .
docker run -p 8501:8501 menu-comparator
```

Share `http://your-server:8501` with your team. The image includes Playwright so live scraping works on the server.

**Note:** Streamlit Community Cloud’s default hosting does not support Playwright browsers. Use Docker/self-host for scrape-from-URL, or use the UI’s “upload menu CSV” path on cloud hosts.

## Adding a new platform scraper

1. Create `scrapers/your_platform.py` subclassing `BaseMenuScraper`.
2. Set `platform_id`, `platform_name`, `url_patterns`, and optional `menu_url_hints` / `dom_selectors`.
3. Implement `matches_url()`.
4. Register the class in `scrapers/registry.py` **before** `GenericScraper`.

Example:

```python
class MyPlatformScraper(BaseMenuScraper):
    platform_id = "my_platform"
    platform_name = "My Platform"
    url_patterns = ("myplatform.com",)

    def matches_url(self, url: str) -> bool:
        return "myplatform.com" in url.lower()
```

The base class tries **network JSON interception** first, then **DOM card parsing**. If Uber or another site changes their API, open DevTools → Network, find the menu payload, and add URL hints to `menu_url_hints`.

## Legal and terms of service

Automated scraping may violate a platform’s Terms of Service. Use this tool only for stores you own or manage, scrape politely (built-in delays), and prefer official APIs or data exports when available. You are responsible for compliance with applicable laws and platform policies.

## Troubleshooting

- **No items scraped**: Run with `--no-headless`, confirm the URL opens a public menu, try `--platform generic`, or inspect Network tab for new JSON endpoints.
- **Wrong matches**: Add rows to `mapping.csv` or rename POS items closer to delivery names.
- **Playwright errors**: Run `playwright install chromium` inside your virtualenv.

## Tests

```bash
pytest -q
```

Tests use sample CSVs only; no live platform scraping in CI.

## Project layout

```
app/              CLI and comparison logic
scrapers/         Pluggable platform scrapers
samples/          Example POS, mapping, and per-platform menus
tests/            Unit tests
app_streamlit.py  Web UI
```

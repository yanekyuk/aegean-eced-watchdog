# Aegean e-ÇED Ecological Watchdog

Lightweight, zero-dependency, open-source watcher and page-cited PDF pre-digest pipeline for Turkey's public Environmental Impact Assessment (*ÇED*) announcements (`https://eced-duyuru.csb.gov.tr/eced-prod/duyurular.xhtml`), tracking **İzmir** and **Manisa (Gediz Basin)**.

## Features

- **Pure HTTP/1.1 JSF/PrimeFaces poller:** No Playwright or headless browser required. Uses `httpx` with `javax.faces.ViewState` rotation, incremental caching, and strict TLS verification via Sectigo's official AIA intermediate CA (`certs/ssl2buy-emea-ov.pem`).
- **Deterministic statutory clocks:** Automatically tracks 10-day *askı*/HKT review windows and the **30-day İYUK Madde 20/A** urgent annulment lawsuit deadline (where İYUK Madde 11 does not pause the clock).
- **Page-cited PDF pre-digests:** Uses `pymupdf` to audit baseline methodology, water/discharge, protected zones, olive groves (*3573*), flora/fauna, and emissions—citing the exact 1-based PDF page (`[s. N]`) for every extracted figure.
- **Static dashboard + RSS 2.0:** Generates a zero-CDN filterable HTML dashboard (`docs/index.html`), standalone per-filing digest pages (`docs/digests/*.html` + `.md`), and an RSS 2.0 feed (`docs/feed.xml`) ready for GitHub Pages and RSS/Telegram alert bots.

## Usage

```bash
# Sync dependencies
uv sync

# Incremental fetch (İzmir + Manisa), digest up to 4 new priority PDFs, build docs/
uv run eced-watch --days 30 --max-digests 4

# Rebuild static site & RSS offline from cached data/filings.json
uv run eced-watch --skip-fetch --skip-digests

# Track additional provinces (standard Turkish plate codes)
uv run eced-watch --provinces 35:İZMİR 45:MANİSA 09:AYDIN --days 14
```

## Automated Daily Deployment (GitHub Actions + Pages)

1. Push this repo to GitHub.
2. Under **Settings → Pages**, set **Source** to **GitHub Actions**.
3. `.github/workflows/daily-watch.yml` runs daily at **07:15 TRT (04:15 UTC)** (and on manual `workflow_dispatch`), commits updated `data/filings.json`, `data/digests/`, and `docs/`, and deploys `docs/` to GitHub Pages.

> **Disclaimer:** Informational transparency aid generated from official public Ministry announcements. Always verify statutory deadlines and legal standing with qualified legal counsel.

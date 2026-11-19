# Türkiye e-ÇED İzleme Platformu (`aegean-eced-watchdog`)

Lightweight, open-source watcher, interactive Türkiye map, statutory deadline tracker, and page-cited PDF pre-digest pipeline for Turkey's public Environmental Impact Assessment (*ÇED*) announcements (`https://eced-duyuru.csb.gov.tr/eced-prod/duyurular.xhtml`) across **all 81 provinces**.

## Features

- **Türkiye-wide pure HTTP/1.1 JSF/PrimeFaces poller:** Polls all 81 provinces in a single chronological pass (or filters to chosen provinces via `--provinces`), with incremental caching and strict TLS verification via Sectigo's official AIA intermediate CA (`certs/ssl2buy-emea-ov.pem`).
- **Interactive Leaflet map & PDF coordinate extraction:** Converts UTM/ED50/WGS84 coordinate tables directly out of official PDFs (`src/eced_watchdog/geo.py`) to plot exact project locations/routes, falling back cleanly to province centroids when coordinates live only inside scanned maps.
- **Deterministic statutory clocks:** Automatically tracks 10-day *askı*/HKT windows and the **30-day İYUK Madde 20/A** urgent annulment lawsuit deadline (where İYUK Madde 11 does not pause the clock).
- **Tiered Gemini synthesis:** Uses `pymupdf` for exact `[s. N]` page indexing, then runs schema-constrained Gemini synthesis when `GEMINI_API_KEY` is set (`gemini-4-hydrogen` for **Ek-1** full ÇED reports; `gemini-3.5-flash-lite` for **Ek-2** PTD files — overrideable via `GEMINI_MODEL` or `--gemini-model`).
- **Turkish public site, guide & RSS 2.0:** Generates `docs/index.html` (map + live province/search filters), `docs/rehber.html` (scientific review guide + template), `docs/digests/*.html` + `.md`, and `docs/feed.xml`.

## Usage

```bash
# Sync dependencies
uv sync

# Nationwide 7-day incremental fetch (all 81 provinces), digest up to 5 new PDFs, build docs/
uv run eced-watch --days 7 --max-digests 5 --drop-pdfs

# Rebuild static site, map & RSS offline from cached data/filings.json
uv run eced-watch --skip-fetch --skip-digests

# Optional: restrict polling to specific provinces (Turkish plate codes)
uv run eced-watch --provinces 35:İZMİR 45:MANİSA 34:İSTANBUL --days 14
```

## Scheduling & Deployment (Turkish IP Note)

`eced-duyuru.csb.gov.tr` silently drops TCP connections from foreign datacenter IP ranges (such as GitHub Actions' US Azure runners), so polling should run from a **Turkish IP** (a local Linux machine or a Turkish VPS):

```bash
# Install daily local systemd user timer (09:00 local, Persistent=true)
chmod +x scripts/install-systemd-timer.sh
./scripts/install-systemd-timer.sh

# Check logs
journalctl --user -u aegean-eced-watchdog.service -n 50
```

When you commit and push updated `data/` + `docs/` to GitHub, `.github/workflows/deploy-pages.yml` validates `docs/index.html` and `docs/feed.xml` and deploys `docs/` to GitHub Pages automatically once the repository is public (or on GitHub Pro).

> **Disclaimer:** Informational transparency aid generated from official public Ministry announcements. Always verify statutory deadlines and legal standing with qualified legal counsel.

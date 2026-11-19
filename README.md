# Aegean e-ÇED Ecological Watchdog

Lightweight, zero-dependency, open-source watcher and page-cited PDF pre-digest pipeline for Turkey's public Environmental Impact Assessment (*ÇED*) announcements (`https://eced-duyuru.csb.gov.tr/eced-prod/duyurular.xhtml`), tracking **İzmir** and **Manisa (Gediz Basin)**.

## Features

- **Pure HTTP/1.1 JSF/PrimeFaces poller:** No Playwright or headless browser required. Uses `httpx` with `javax.faces.ViewState` rotation, incremental caching, and strict TLS verification via Sectigo's official AIA intermediate CA (`certs/ssl2buy-emea-ov.pem`).
- **Deterministic statutory clocks:** Automatically tracks 10-day *askı*/HKT review windows and the **30-day İYUK Madde 20/A** urgent annulment lawsuit deadline (where İYUK Madde 11 does not pause the clock).
- **Page-cited PDF pre-digests + optional Gemini synthesis:** Uses `pymupdf` to audit baseline methodology, water/discharge, protected zones, olive groves (*3573*), flora/fauna, and emissions—citing the exact 1-based PDF page (`[s. N]`) for every extracted figure. When `GEMINI_API_KEY` is set (environment or gitignored `.env`), runs an optional schema-constrained **`gemini-4-hydrogen`** synthesis pass (overrideable via `GEMINI_MODEL` or `--gemini-model`) over the top ~26 highest-signal pages to generate plain Turkish/English summaries, baseline assessments, red flags, and draft HKT/İYUK 20/A questions with `[s. N]` citations.
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

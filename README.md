# Türkiye e-ÇED İzleme Platformu

Open-source, low-maintenance watcher, interactive Türkiye map, statutory deadline monitor, and page-cited PDF pre-digest pipeline for Turkey's public Environmental Impact Assessment (*ÇED*) announcements (`https://eced-duyuru.csb.gov.tr/eced-prod/duyurular.xhtml`) across **all 81 provinces**.

---

## End-to-End Architecture & Data Flow

```text
eced-duyuru.csb.gov.tr (JSF / PrimeFaces Portal)
   │  [1] fetcher.py — Pure HTTP/1.1 + ViewState poller (Turkish IP, strict TLS via Sectigo AIA cert)
   ▼
data/filings.json (Canonical lifecycle registry + deterministic 10d askı & 30d İYUK 20/A clocks)
   │  [2] digest.py + geo.py — PyMuPDF text/table scan + UTM/ED50/WGS84 PDF coordinate extraction
   │  [3] llm.py — Optional tiered Gemini API synthesis over top ~26 high-signal pages (Pydantic JSON)
   ▼
data/digests/<id>_analysis.json + <id>_digest.md (Cached; never re-billed on subsequent runs)
   │  [4] site.py — Static Turkish HTML dashboard, interactive Leaflet maps, rehber.html & RSS 2.0
   ▼
docs/ (index.html, rehber.html, feed.xml, digests/*.html + *.md)
   │  [5] git push -> .github/workflows/deploy-pages.yml (XML/HTML check + GitHub Pages deploy)
   ▼
Live Public Website & RSS 2.0 Feed
```

---

## Sorting & Prioritization

Both the **public dashboard** and the **automated PDF digest queue** prioritize **statutory urgency** so critical deadlines never get buried under newer filings:

1. **Active dated clocks (ascending by days remaining):** Filings with `0`, `1`, `2`, … days left on their 10-day *askı* or 30-day **İYUK Madde 20/A** lawsuit clock appear at the very top.
2. **Active undated notices (HKT / İDK):** Ordered newest first.
3. **Expired records:** Ordered newest first at the bottom.

On the website (`docs/index.html`), users can also switch live via the **Sıralama** dropdown between *En acil yasal süre* (default), *En yeni duyuru*, *Ön özeti hazır olanlar*, and *Ek-1 öncelikli*, alongside the 81-province `<select>` filter, search box, and synced Leaflet map.

---

## Step-by-Step: Generating LLM Reports & Publishing

### 1. Install Dependencies

Requires Python 3.12+ and [`uv`](https://docs.astral.sh/uv/):

```bash
uv sync
```

### 2. Configure the Gemini API Key (Optional LLM Layer)

Without an API key, `eced-watch` still runs 100% deterministically (PyMuPDF page-cited extraction, statutory clocks, coordinate extraction, maps, and RSS).

To enable **schema-constrained Gemini scientific synthesis** (Turkish/English executive summaries, baseline/seasonal-sampling audits, `[s. N]` red flags, and draft HKT / İYUK 20/A technical questions), create a local gitignored `.env` file in the repository root (or export `GEMINI_API_KEY` in your shell):

```bash
cat > .env <<'EOF'
GEMINI_API_KEY=your_gemini_api_key_here
# Optional: force one model for all filings (overrides automatic Ek-1 / Ek-2 tiering)
# GEMINI_MODEL=gemini-4-hydrogen
EOF
chmod 600 .env
```

**How tiered synthesis works (`src/eced_watchdog/llm.py`):**
- **Focused context:** Never sends an entire 900-page raw PDF. `select_high_signal_pages()` selects up to ~26 highest-signal pages (*Teknik Olmayan Özet*, *Bölüm II*, *Flora/Fauna*, *Kümülatif Etki*, water/olive/emission hits) tagged with `=== PDF PAGE [s. N] ===`.
- **Automatic model tiering** (unless `GEMINI_MODEL` or `--gemini-model` is set):
  - **Ek-1** (full ÇED reports) → **`gemini-4-hydrogen`**
  - **Ek-2** (PTD files) → **`gemini-3.5-flash-lite`**
- **Strict Pydantic JSON output & retry:** Every extracted fact, finding, and question requires explicit 1-based `[s. N]` page citations, with automatic exponential backoff retry on transient `503`/`429` responses.
- **Caching:** Synthesis output is stored inside `data/digests/<id>_analysis.json` so existing filings are never re-synthesized unless you explicitly pass `--re-synthesize`.

### 3. Run the Pipeline Locally

#### Recommended: Interactive All-in-One Publish Flow (`eced-publish`)
Fetches the latest nationwide announcements, finds every filing still missing an LLM report (sorted by fewest days remaining), prints a **live USD cost estimate** (`Next 5`, `Next 10`, `Next 25`, `All Ek-1`, `All pending`), asks how many you want to generate, generates them (tracking real token usage), rebuilds `docs/` + validates `feed.xml`, and prompts to commit and push:

```bash
uv run eced-publish
# Or skip live fetch and inspect/generate from cached filings only:
uv run eced-publish --skip-fetch
```

#### Headless / Scriptable CLI (`eced-watch`)
```bash
# Standard nationwide run (last 7 days across all 81 provinces, up to 5 new PDFs, clean up raw PDFs)
uv run eced-watch --days 7 --max-digests 5 --drop-pdfs

# Backfill LLM synthesis on already-cached digests without polling the portal
uv run eced-watch --skip-fetch --max-digests 0

# Re-run LLM synthesis with a specific model on cached digests
uv run eced-watch --skip-fetch --max-digests 0 --re-synthesize --gemini-model gemini-4-neon

# Rebuild static site, maps & RSS completely offline from data/
uv run eced-watch --skip-fetch --skip-digests

# Deterministic-only run (disable Gemini even if .env is present)
uv run eced-watch --days 7 --max-digests 5 --skip-llm

# Optional: poll specific provinces only (Turkish plate codes)
uv run eced-watch --provinces 35:İZMİR 45:MANİSA 34:İSTANBUL --days 14
```

### 4. Publish to GitHub Pages

#### One-time GitHub setup
1. Push this repository to GitHub (public repository, or GitHub Pro for private Pages).
2. In **Settings → Pages**, set **Source** to **GitHub Actions**.
3. Pass your public Pages URL via `--site-url` (or update the default in `src/eced_watchdog/cli.py`) so `docs/feed.xml` links directly to your hosted digest pages.

#### Publishing updates
Commit and push the generated `data/` and `docs/` files (raw PDFs in `data/pdfs/` and `.env` are strictly ignored via `.gitignore`):

```bash
git add data/ docs/
git commit -m "chore(watch): daily nationwide e-ÇED update ($(date +%Y-%m-%d))"
git push
```

Every push to `main` touching `docs/**` automatically triggers `.github/workflows/deploy-pages.yml`, which:
1. Validates `docs/index.html` and verifies `docs/feed.xml` is well-formed RSS 2.0 XML.
2. Uploads and deploys `docs/` to GitHub Pages (~15–25 seconds).

---

## Daily Automated Scheduling (Turkish IP Requirement)

`eced-duyuru.csb.gov.tr` silently drops TCP connections from foreign datacenter IP ranges (such as GitHub Actions' US Azure runners), so polling must run from a **Turkish IP** (a local Linux desktop/laptop or a Turkish VPS).

Install the included `systemd --user` daily timer (`09:00` local time, `Persistent=true` catches up on wake, automatically loads `.env` if present):

```bash
chmod +x scripts/install-systemd-timer.sh
./scripts/install-systemd-timer.sh

# Inspect timer schedule and logs
systemctl --user list-timers
journalctl --user -u eced-watchdog.service -n 50 --no-pager
```

---

## CLI Options Reference

| Flag | Default | Purpose |
|---|---|---|
| `--days N` | `7` | Lookback window in days |
| `--provinces CODE:LABEL ...` | *(all 81)* | Restrict polling to chosen provinces |
| `--max-digests N` | `5` | Max newly downloaded & synthesized PDFs per run |
| `--workers N` | `4` | Parallel workers for PDF parsing & Gemini synthesis (Ministry PDF downloads remain capped at 2 concurrent) |
| `--drop-pdfs` | `false` | Delete raw PDFs after extraction/synthesis |
| `--skip-fetch` | `false` | Skip portal polling; use existing `data/filings.json` |
| `--skip-digests` | `false` | Skip PDF extraction & LLM synthesis; rebuild `docs/` only |
| `--skip-llm` | `false` | Run deterministic PyMuPDF extraction without Gemini |
| `--re-synthesize` | `false` | Force fresh Gemini synthesis on already-digested PDFs |
| `--gemini-model ID` | *tiered* | Override default `Ek-1` / `Ek-2` model selection |
| `--site-url URL` | GitHub Pages URL | Base URL written into `docs/feed.xml` |

> **Disclaimer:** Informational transparency aid generated from official public Ministry announcements. Under Article 20/A of Turkey's Administrative Procedure Law (İYUK), annulment lawsuits against ÇED decisions carry a 30-day statutory clock that is **not** tolled by İYUK Article 11 administrative applications. Always verify deadlines and legal standing with qualified counsel.

"""Static HTML dashboard, per-filing digest HTML renderer, and RSS 2.0 feed builder."""

from __future__ import annotations

import html
import json
import shutil
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

BASE_CSS = """
:root {
  --bg: #0f1216;
  --surface: #171c22;
  --border: #262e38;
  --text: #e6edf3;
  --muted: #8b949e;
  --accent: #58a6ff;
  --red: #f85149;
  --amber: #d29922;
  --green: #3fb950;
  --badge-bg: #212830;
}
@media (prefers-color-scheme: light) {
  :root {
    --bg: #f6f8fa;
    --surface: #ffffff;
    --border: #d0d7de;
    --text: #1f2328;
    --muted: #656d76;
    --accent: #0969da;
    --red: #cf222e;
    --amber: #9a6700;
    --green: #1a7f37;
    --badge-bg: #eef2f6;
  }
}
* { box-sizing: border-box; }
body {
  margin: 0;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  background: var(--bg);
  color: var(--text);
  line-height: 1.5;
}
.wrap { max-width: 1220px; margin: 0 auto; padding: 24px 18px 64px; }
a { color: var(--accent); text-decoration: none; }
a:hover { text-decoration: underline; }
header { border-bottom: 1px solid var(--border); padding-bottom: 16px; margin-bottom: 20px; }
h1 { margin: 0 0 6px; font-size: 1.55rem; }
.sub { color: var(--muted); font-size: 0.92rem; margin: 0; }
.meta-bar { display: flex; flex-wrap: wrap; gap: 12px; margin-top: 12px; font-size: 0.85rem; color: var(--muted); }
.stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; margin: 16px 0 20px; }
.stat { background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 12px 14px; }
.stat .num { font-size: 1.45rem; font-weight: 700; }
.stat .lbl { font-size: 0.78rem; color: var(--muted); }
.controls { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-bottom: 16px; }
input[type="search"] {
  flex: 1 1 240px;
  padding: 8px 12px;
  border-radius: 6px;
  border: 1px solid var(--border);
  background: var(--surface);
  color: var(--text);
  font-size: 0.92rem;
}
button.pill {
  padding: 6px 11px;
  border-radius: 999px;
  border: 1px solid var(--border);
  background: var(--surface);
  color: var(--text);
  cursor: pointer;
  font-size: 0.82rem;
}
button.pill.active { background: var(--accent); border-color: var(--accent); color: #fff; font-weight: 600; }
.cards { display: flex; flex-direction: column; gap: 10px; }
.card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 14px 16px;
}
.card.prio { border-left: 4px solid var(--accent); }
.row-top { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 8px; align-items: baseline; }
.title { font-weight: 600; font-size: 0.98rem; }
.badges { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 6px; }
.badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 0.75rem;
  background: var(--badge-bg);
  border: 1px solid var(--border);
}
.badge.urgent { border-color: var(--red); color: var(--red); font-weight: 600; }
.badge.warn { border-color: var(--amber); color: var(--amber); font-weight: 600; }
.badge.ok { border-color: var(--green); color: var(--green); }
.badge.muted { color: var(--muted); }
.detail { font-size: 0.86rem; color: var(--muted); margin: 8px 0; }
.actions { display: flex; flex-wrap: wrap; gap: 12px; font-size: 0.84rem; margin-top: 8px; }
.notice {
  margin-top: 28px;
  padding: 12px 14px;
  border: 1px solid var(--border);
  border-radius: 8px;
  font-size: 0.82rem;
  color: var(--muted);
}
table.kv { width: 100%; border-collapse: collapse; margin: 12px 0; font-size: 0.9rem; }
table.kv th, table.kv td { border: 1px solid var(--border); padding: 8px 10px; text-align: left; vertical-align: top; }
table.kv th { width: 220px; background: var(--badge-bg); }
code { background: var(--badge-bg); padding: 1px 5px; border-radius: 4px; font-size: 0.85em; }
blockquote { margin: 10px 0; padding: 10px 14px; border-left: 3px solid var(--accent); background: var(--surface); font-size: 0.9rem; }
.hit { margin: 6px 0; font-size: 0.88rem; }
.pno { font-weight: 700; color: var(--accent); }
"""


def _esc(val: Any) -> str:
    return html.escape(str(val or ""), quote=True)


def _best_active_clock(filing: dict[str, Any]) -> dict[str, Any] | None:
    clocks = filing.get("statutory_clocks") or []
    dated = [c for c in clocks if c.get("days_remaining") is not None]
    if dated:
        dated.sort(key=lambda c: c["days_remaining"])
        return dated[0]
    return clocks[0] if clocks else None


def _clock_badge_html(clock: dict[str, Any] | None) -> str:
    if not clock:
        return ""
    dr = clock.get("days_remaining")
    code = clock.get("code", "")
    label = {
        "iyuk_20a": "İYUK 20/A",
        "aski_10d": "10d Askı",
        "hkt": "HKT",
        "idk": "İDK",
    }.get(code, "Clock")
    if dr is None:
        return f'<span class="badge warn">{_esc(label)} · check date</span>'
    if dr < 0:
        return f'<span class="badge muted">{_esc(label)} · expired ({clock["deadline"]})</span>'
    if dr <= 7:
        return f'<span class="badge urgent">{_esc(label)} · {dr}d left ({clock["deadline"]})</span>'
    if dr <= 15:
        return f'<span class="badge warn">{_esc(label)} · {dr}d left ({clock["deadline"]})</span>'
    return f'<span class="badge ok">{_esc(label)} · {dr}d left ({clock["deadline"]})</span>'


def render_digest_html(saved: dict[str, Any], raw_md_filename: str) -> str:
    filing = saved["filing"]
    docs = filing.get("documents") or [{}]
    doc_meta = docs[0]
    pdf_info = saved["pdf_info"]
    analysis = saved["analysis"]
    filing_id = doc_meta.get("filing_id") or "unknown"
    pdf_url = doc_meta["pdf_urls"][0]["url"] if doc_meta.get("pdf_urls") else ""

    checks = analysis["audit_checks"]
    check_rows = [
        ("Field survey (*arazi/saha çalışması*)", checks["mentions_field_survey"]),
        ("Literature review (*literatür taraması*)", checks["mentions_literature_only_cue"]),
        ("Seasonal sampling (*mevsimsel*)", checks["mentions_seasonal_sampling"]),
        ("Cumulative impact (*kümülatif*)", checks["mentions_cumulative_impact"]),
        ("Olive Law / groves (*3573 / zeytinlik*)", checks["mentions_olive_law_3573"]),
        ("Groundwater / aquifer (*akifer / yeraltı suyu*)", checks["mentions_groundwater_or_aquifer"]),
        ("Endemic / IUCN / Bern Convention", checks["mentions_iucn_or_endemic"]),
    ]
    checks_html = "\n".join(
        f"<tr><th>{_esc(lbl)}</th><td>"
        + ('<span class="badge ok">Present</span>' if ok else '<span class="badge urgent">NOT FOUND (check manually)</span>')
        + "</td></tr>"
        for lbl, ok in check_rows
    )

    sig_blocks: list[str] = []
    for _k, sig in analysis["signals"].items():
        pages_preview = ", ".join(f"s.{p}" for p in sig["pages"][:14])
        if sig["page_count"] > 14:
            pages_preview += f" (+{sig['page_count'] - 14} more)"
        hits_html = "\n".join(
            f'<div class="hit"><span class="pno">[s. {h["page"]}]</span> <code>{_esc(h["match"])}</code> — {_esc(h["snippet"])}</div>'
            for h in sig["samples"][:6]
        ) or '<div class="hit" style="color:var(--muted)">No text matches found.</div>'
        sig_blocks.append(
            f'<section class="card"><h3>{_esc(sig["label"])} '
            f'<span style="color:var(--muted);font-weight:400;font-size:0.85rem">({sig["page_count"]} pages: {_esc(pages_preview or "none")})</span></h3>'
            f"{hits_html}</section>"
        )

    headings_html = "\n".join(
        f'<li><span class="pno">[s. {pno}]</span> {_esc(h)}</li>'
        for pno, h in analysis.get("headings", [])[:20]
    )

    clocks_html = " ".join(_clock_badge_html(c) for c in filing.get("statutory_clocks") or [])

    return f"""<!doctype html>
<html lang="tr">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>e-ÇED Pre-Digest #{_esc(filing_id)} — {_esc(filing['district'])}</title>
  <style>{BASE_CSS}</style>
</head>
<body>
<div class="wrap">
  <header>
    <div style="font-size:0.85rem;margin-bottom:8px;"><a href="../index.html">← Back to Aegean e-ÇED Watchdog</a> · <a href="{_esc(raw_md_filename)}">Raw Markdown (.md)</a></div>
    <h1>e-ÇED Pre-Digest #{_esc(filing_id)} — {_esc(filing['district'])} / {_esc(filing['province'])}</h1>
    <p class="sub">{_esc(filing['project_name'])}</p>
    <div class="badges" style="margin-top:10px;">
      <span class="badge">{_esc(filing['decision_type'])}</span>
      <span class="badge">{_esc(filing['project_type'])}</span>
      {clocks_html}
    </div>
  </header>

  <table class="kv">
    <tr><th>Project Owner</th><td>{_esc(filing['project_owner'])}</td></tr>
    <tr><th>Consulting Firm</th><td>{_esc(doc_meta.get('consulting_firm') or '—')}</td></tr>
    <tr><th>Sector</th><td>{_esc(filing['sector'])} / {_esc(filing['sub_sector'])}</td></tr>
    <tr><th>Announcement Date</th><td><code>{_esc(filing['announcement_date_tr'])}</code> (uploaded <code>{_esc(doc_meta.get('submitted_at') or '—')}</code>)</td></tr>
    <tr><th>PDF Coverage</th><td>{pdf_info['bytes'] / 1024 / 1024:.2f} MB · {analysis['page_count']} pages ({analysis['text_pages']} text / {analysis['scanned_or_blank_pages']} scanned-or-image) · SHA-256 <code>{_esc(pdf_info['sha256'][:16])}…</code></td></tr>
    <tr><th>Official Links</th><td><a href="{_esc(doc_meta.get('portal_doc_url', ''))}" target="_blank" rel="noopener">e-ÇED Portal Record</a> · <a href="{_esc(pdf_url)}" target="_blank" rel="noopener">Official PDF</a></td></tr>
  </table>

  <h2>Official Announcement Text</h2>
  <blockquote>{_esc(filing.get('detail_text', ''))}</blockquote>

  <h2>Automated Baseline &amp; Red-Flag Scan</h2>
  <table class="kv">{checks_html}</table>
  <p class="sub">Scanned annex maps/letters without OCR are excluded from automated text scan.</p>

  <h2>Page-Cited Extracted Evidence</h2>
  <div class="cards">{''.join(sig_blocks)}</div>

  <h2>Document Navigation Map</h2>
  <ul>{headings_html or '<li style="color:var(--muted)">No structured headings detected.</li>'}</ul>

  <div class="notice">
    Informational civic transparency aid generated from official public Ministry announcements at <code>eced-duyuru.csb.gov.tr</code>. Every figure cites its 1-based PDF page <code>[s. N]</code>. Statutory deadlines are computed automatically and must be verified by qualified legal counsel.
  </div>
</div>
</body>
</html>
"""


def build_rss(filings: list[dict[str, Any]], digests_index: set[str], site_url: str) -> str:
    rss = ET.Element("rss", version="2.0")
    channel = ET.SubElement(rss, "channel")
    ET.SubElement(channel, "title").text = "Aegean e-ÇED Ecological Watchdog (İzmir & Manisa)"
    ET.SubElement(channel, "link").text = site_url
    ET.SubElement(channel, "description").text = (
        "Automated daily tracker for Turkey's public e-ÇED announcements in İzmir and Manisa, "
        "with statutory 10-day askı and 30-day İYUK 20/A countdowns and page-cited PDF digests."
    )
    ET.SubElement(channel, "language").text = "tr"
    ET.SubElement(channel, "lastBuildDate").text = format_datetime(datetime.now(timezone.utc))

    for f in filings[:50]:
        docs = f.get("documents") or []
        doc_meta = docs[0] if docs else {}
        filing_id = doc_meta.get("filing_id")
        portal_url = doc_meta.get("portal_doc_url") or "https://eced-duyuru.csb.gov.tr/eced-prod/duyurular.xhtml"
        pdf_url = doc_meta["pdf_urls"][0]["url"] if doc_meta.get("pdf_urls") else None

        item = ET.SubElement(channel, "item")
        prio_prefix = "[PRIO] " if f.get("priority_district") else ""
        ET.SubElement(item, "title").text = (
            f"{prio_prefix}[{f['province']}/{f['district']}] {f['decision_type']} — {f['project_name']}"
        )
        if filing_id and filing_id in digests_index and site_url.startswith("http"):
            ET.SubElement(item, "link").text = f"{site_url.rstrip('/')}/digests/{filing_id}.html"
        else:
            ET.SubElement(item, "link").text = portal_url

        guid = ET.SubElement(item, "guid", isPermaLink="false")
        guid.text = f.get("filing_key") or portal_url

        ann_iso = f.get("announcement_date")
        if ann_iso:
            dt = datetime.fromisoformat(ann_iso).replace(tzinfo=timezone.utc)
            ET.SubElement(item, "pubDate").text = format_datetime(dt)

        clocks_txt = "; ".join(
            f"{c['kind']}: {c['deadline']} ({c['days_remaining']}d left)"
            if c.get("deadline")
            else c["kind"]
            for c in f.get("statutory_clocks") or []
        )
        desc_parts = [
            f"Owner: {f.get('project_owner', '')}",
            f"Sector: {f.get('sector', '')} / {f.get('sub_sector', '')} ({f.get('project_type', '')})",
            f"Clocks: {clocks_txt or '—'}",
            f"Official record: {portal_url}",
        ]
        if pdf_url:
            desc_parts.append(f"Official PDF: {pdf_url}")
        if filing_id and filing_id in digests_index:
            desc_parts.append(f"Page-cited digest: digests/{filing_id}.html")
        if f.get("detail_text"):
            desc_parts.append("")
            desc_parts.append(f["detail_text"])
        ET.SubElement(item, "description").text = "\n".join(desc_parts)

    ET.indent(rss, space="  ")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(rss, encoding="unicode")


def build_site(
    filings: list[dict[str, Any]],
    *,
    digests_dir: Path,
    docs_dir: Path,
    site_url: str = "https://eced-duyuru.csb.gov.tr/eced-prod/duyurular.xhtml",
) -> dict[str, Any]:
    docs_dir.mkdir(parents=True, exist_ok=True)
    docs_digests = docs_dir / "digests"
    docs_digests.mkdir(parents=True, exist_ok=True)

    # Render HTML + copy MD for every available digest
    digests_index: set[str] = set()
    if digests_dir.exists():
        for json_file in sorted(digests_dir.glob("*_analysis.json")):
            saved = json.loads(json_file.read_text(encoding="utf-8"))
            fid = json_file.name.replace("_analysis.json", "")
            md_src = digests_dir / f"{fid}_digest.md"
            md_dst_name = f"{fid}.md"
            if md_src.exists():
                shutil.copyfile(md_src, docs_digests / md_dst_name)
            html_out = render_digest_html(saved, md_dst_name)
            (docs_digests / f"{fid}.html").write_text(html_out, encoding="utf-8")
            digests_index.add(fid)

    # Stats
    total = len(filings)
    prio_count = sum(1 for f in filings if f.get("priority_district"))
    active_count = sum(
        1
        for f in filings
        if any(
            c.get("days_remaining") is None or c.get("days_remaining", -1) >= 0
            for c in f.get("statutory_clocks") or []
        )
    )
    digested_count = sum(
        1
        for f in filings
        if (f.get("documents") or [{}])[0].get("filing_id") in digests_index
    )

    cards_html: list[str] = []
    for f in filings:
        docs = f.get("documents") or []
        doc_meta = docs[0] if docs else {}
        fid = doc_meta.get("filing_id") or ""
        portal_url = doc_meta.get("portal_doc_url") or ""
        pdf_url = doc_meta["pdf_urls"][0]["url"] if doc_meta.get("pdf_urls") else ""
        has_digest = fid in digests_index
        clock = _best_active_clock(f)
        is_active = any(
            c.get("days_remaining") is None or c.get("days_remaining", -1) >= 0
            for c in f.get("statutory_clocks") or []
        )
        prio = bool(f.get("priority_district"))

        search_blob = " ".join(
            [
                f.get("province", ""),
                f.get("district", ""),
                f.get("project_name", ""),
                f.get("project_owner", ""),
                f.get("sector", ""),
                f.get("sub_sector", ""),
                f.get("decision_type", ""),
                f.get("detail_text", ""),
                fid,
            ]
        ).lower()

        actions = []
        if has_digest:
            actions.append(f'<a href="digests/{_esc(fid)}.html"><strong>Page-Cited Digest</strong></a>')
            actions.append(f'<a href="digests/{_esc(fid)}.md">Raw .md</a>')
        if portal_url:
            actions.append(f'<a href="{_esc(portal_url)}" target="_blank" rel="noopener">e-ÇED Record #{_esc(fid)}</a>')
        if pdf_url:
            actions.append(f'<a href="{_esc(pdf_url)}" target="_blank" rel="noopener">Official PDF</a>')

        detail_short = (f.get("detail_text") or "")[:320]
        if len(f.get("detail_text") or "") > 320:
            detail_short += "…"

        cards_html.append(
            f"""<article class="card {'prio' if prio else ''}"
  data-province="{_esc(f.get('province', ''))}"
  data-prio="{'1' if prio else '0'}"
  data-active="{'1' if is_active else '0'}"
  data-digest="{'1' if has_digest else '0'}"
  data-annex="{_esc(f.get('project_type', ''))}"
  data-search="{_esc(search_blob)}">
  <div class="row-top">
    <div class="title">{_esc(f.get('project_name', ''))}</div>
    <div style="font-size:0.82rem;color:var(--muted);white-space:nowrap;">{_esc(f.get('announcement_date_tr', ''))}</div>
  </div>
  <div class="badges">
    <span class="badge">{_esc(f.get('province', ''))} · {_esc(f.get('district', ''))}</span>
    {'<span class="badge ok">Priority Corridor</span>' if prio else ''}
    <span class="badge">{_esc(f.get('decision_type', ''))}</span>
    <span class="badge">{_esc(f.get('project_type', ''))}</span>
    <span class="badge muted">{_esc(f.get('sector', ''))}</span>
    {_clock_badge_html(clock)}
  </div>
  <div class="detail"><strong>{_esc(f.get('project_owner', ''))}</strong> — {_esc(detail_short)}</div>
  <div class="actions">{' · '.join(actions)}</div>
</article>"""
        )

    provinces_present = sorted({f.get("province", "") for f in filings if f.get("province")})
    prov_buttons = "\n".join(
        f'<button class="pill" data-filter="prov:{_esc(p)}">{_esc(p)}</button>'
        for p in provinces_present
    )

    built_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    index_html = f"""<!doctype html>
<html lang="tr">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>Aegean e-ÇED Ecological Watchdog</title>
  <link rel="alternate" type="application/rss+xml" title="Aegean e-ÇED Watchdog RSS" href="feed.xml" />
  <style>{BASE_CSS}</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>Aegean e-ÇED Ecological Watchdog</h1>
    <p class="sub">Public e-ÇED registry tracker, statutory deadline monitor (10-day askı &amp; 30-day İYUK 20/A), and page-cited PDF pre-digests for İzmir &amp; Manisa (Gediz Basin).</p>
    <div class="meta-bar">
      <span>Updated: <code>{_esc(built_at)}</code></span>
      <span><a href="feed.xml">RSS 2.0 Feed (feed.xml)</a></span>
      <span>Source: <a href="https://eced-duyuru.csb.gov.tr/eced-prod/duyurular.xhtml" target="_blank" rel="noopener">eced-duyuru.csb.gov.tr</a></span>
    </div>
  </header>

  <section class="stats">
    <div class="stat"><div class="num">{total}</div><div class="lbl">Tracked Filings</div></div>
    <div class="stat"><div class="num">{prio_count}</div><div class="lbl">Priority Corridor</div></div>
    <div class="stat"><div class="num">{active_count}</div><div class="lbl">Active Clocks</div></div>
    <div class="stat"><div class="num">{digested_count}</div><div class="lbl">Page-Cited Digests</div></div>
  </section>

  <section class="controls">
    <input id="q" type="search" placeholder="Search district, project, owner, sector, filing ID…" />
    <button class="pill active" data-filter="all">All</button>
    <button class="pill" data-filter="prio">Priority Corridor</button>
    <button class="pill" data-filter="active">Active Clocks</button>
    <button class="pill" data-filter="digest">With Digest</button>
    <button class="pill" data-filter="ek1">Ek-1 Only</button>
    {prov_buttons}
  </section>

  <div id="count" class="sub" style="margin-bottom:10px;">Showing {total} filings</div>
  <main class="cards" id="cards">
    {''.join(cards_html)}
  </main>

  <div class="notice">
    <strong>Informational aid only:</strong> All entries are fetched verbatim from Turkey's public Ministry of Environment e-ÇED portal. Under İYUK Madde 20/A, annulment lawsuits against ÇED decisions carry a 30-day filing clock that is <em>not</em> paused by İYUK 11 administrative applications. Always verify dates and legal standing with qualified counsel.
  </div>
</div>
<script>
(() => {{
  const cards = [...document.querySelectorAll('#cards article')];
  const pills = [...document.querySelectorAll('button.pill')];
  const q = document.getElementById('q');
  const countEl = document.getElementById('count');
  let mode = 'all';

  function apply() {{
    const term = q.value.trim().toLowerCase();
    let shown = 0;
    for (const c of cards) {{
      let ok = true;
      if (mode === 'prio') ok = c.dataset.prio === '1';
      else if (mode === 'active') ok = c.dataset.active === '1';
      else if (mode === 'digest') ok = c.dataset.digest === '1';
      else if (mode === 'ek1') ok = c.dataset.annex === 'Ek-1';
      else if (mode.startsWith('prov:')) ok = c.dataset.province === mode.slice(5);
      if (ok && term) ok = c.dataset.search.includes(term);
      c.style.display = ok ? '' : 'none';
      if (ok) shown++;
    }}
    countEl.textContent = `Showing ${{shown}} of ${{cards.length}} filings`;
  }}

  pills.forEach(p => p.addEventListener('click', () => {{
    pills.forEach(x => x.classList.remove('active'));
    p.classList.add('active');
    mode = p.dataset.filter;
    apply();
  }}));
  q.addEventListener('input', apply);
}})();
</script>
</body>
</html>
"""
    (docs_dir / "index.html").write_text(index_html, encoding="utf-8")
    rss_xml = build_rss(filings, digests_index, site_url)
    (docs_dir / "feed.xml").write_text(rss_xml, encoding="utf-8")

    return {
        "total": total,
        "priority": prio_count,
        "active": active_count,
        "digests_rendered": len(digests_index),
        "index_path": str(docs_dir / "index.html"),
        "feed_path": str(docs_dir / "feed.xml"),
    }

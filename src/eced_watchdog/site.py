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
        "aski_10d": "10g Askı",
        "hkt": "HKT",
        "idk": "İDK",
    }.get(code, "Süre")
    if dr is None:
        return f'<span class="badge warn">{_esc(label)} · tarihi kontrol et</span>'
    if dr < 0:
        return f'<span class="badge muted">{_esc(label)} · süre doldu ({clock["deadline"]})</span>'
    if dr <= 7:
        return f'<span class="badge urgent">{_esc(label)} · {dr} gün kaldı ({clock["deadline"]})</span>'
    if dr <= 15:
        return f'<span class="badge warn">{_esc(label)} · {dr} gün kaldı ({clock["deadline"]})</span>'
    return f'<span class="badge ok">{_esc(label)} · {dr} gün kaldı ({clock["deadline"]})</span>'


TR_SIGNAL_LABELS = {
    "coordinates_and_footprint": "Koordinatlar, Parsel ve Alan Büyüklüğü",
    "water_and_discharge": "Su Kullanımı, Hidrojeoloji ve Deşarj",
    "protected_land_and_olive": "Korunan Alanlar, Orman ve Zeytinlikler",
    "ecology_and_baseline": "Flora, Fauna ve Saha Metodolojisi",
    "pollutants_and_hazards": "Emisyonlar, Jeokimya ve Atıklar",
    "cost_and_capacity": "Proje Bedeli, Güç ve Kapasite",
}

TR_BASELINE_STATUS = {
    "field_survey_documented": "Belgelenmiş saha çalışması",
    "literature_only": "Yalnızca literatür",
    "mixed_or_unclear": "Karışık / belirsiz",
    "not_found": "Bulunamadı",
    "completed_pre_project": "Önceden tamamlanmış",
    "promised_post_approval_only": "Yalnızca onay sonrasına taahhüt",
    "unclear": "Belirsiz",
    "quantitatively_assessed": "Nicel değerlendirme var",
    "superficial_or_boilerplate": "Yüzeysel / şablon",
    "omitted_or_not_found": "Eksik / bulunamadı",
}

TR_SEVERITY = {
    "high": "YÜKSEK",
    "medium": "ORTA",
    "low": "DÜŞÜK",
}


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
        ("Saha / arazi çalışması geçiyor mu", checks["mentions_field_survey"]),
        ("Literatür taraması ifadesi geçiyor mu", checks["mentions_literature_only_cue"]),
        ("Mevsimsel örnekleme geçiyor mu", checks["mentions_seasonal_sampling"]),
        ("Kümülatif etki değerlendirmesi geçiyor mu", checks["mentions_cumulative_impact"]),
        ("Zeytincilik Kanunu (3573 / zeytinlik)", checks["mentions_olive_law_3573"]),
        ("Yeraltı suyu / akifer / hidrojeoloji", checks["mentions_groundwater_or_aquifer"]),
        ("Endemik tür / IUCN / Bern Sözleşmesi", checks["mentions_iucn_or_endemic"]),
    ]
    checks_html = "\n".join(
        f"<tr><th>{_esc(lbl)}</th><td>"
        + ('<span class="badge ok">Metinde var</span>' if ok else '<span class="badge urgent">BULUNAMADI (elle kontrol edin)</span>')
        + "</td></tr>"
        for lbl, ok in check_rows
    )

    sig_blocks: list[str] = []
    for k, sig in analysis["signals"].items():
        tr_label = TR_SIGNAL_LABELS.get(k, sig["label"])
        pages_preview = ", ".join(f"s.{p}" for p in sig["pages"][:14])
        if sig["page_count"] > 14:
            pages_preview += f" (+{sig['page_count'] - 14} sayfa)"
        hits_html = "\n".join(
            f'<div class="hit"><span class="pno">[s. {h["page"]}]</span> <code>{_esc(h["match"])}</code> — {_esc(h["snippet"])}</div>'
            for h in sig["samples"][:6]
        ) or '<div class="hit" style="color:var(--muted)">Eşleşen metin bulunamadı.</div>'
        sig_blocks.append(
            f'<section class="card"><h3>{_esc(tr_label)} '
            f'<span style="color:var(--muted);font-weight:400;font-size:0.85rem">({sig["page_count"]} sayfa: {_esc(pages_preview or "yok")})</span></h3>'
            f"{hits_html}</section>"
        )

    headings_html = "\n".join(
        f'<li><span class="pno">[s. {pno}]</span> {_esc(h)}</li>'
        for pno, h in analysis.get("headings", [])[:20]
    )

    clocks_html = " ".join(_clock_badge_html(c) for c in filing.get("statutory_clocks") or [])

    llm_block = ""
    llm = saved.get("llm_synthesis")
    if llm and llm.get("result"):
        res = llm["result"]
        ba = res["baseline_assessment"]
        pages_used = ", ".join(f"s.{p}" for p in llm.get("pages_sent") or [])
        facts_html = "\n".join(
            f'<tr><th>{_esc(kf["label"])}</th><td>{_esc(kf["value"])} <span class="pno">[s. {kf["page"]}]</span></td></tr>'
            for kf in res.get("key_facts") or []
        )
        sev_cls = {"high": "urgent", "medium": "warn", "low": "muted"}
        flags_html = "\n".join(
            f'<div class="hit"><span class="badge {sev_cls.get(rf["severity"], "muted")}">{_esc(TR_SEVERITY.get(rf["severity"], rf["severity"].upper()))}</span> '
            f'<strong>{_esc(rf["title"])}</strong> '
            f'<span class="pno">[{", ".join(f"s. {p}" for p in rf.get("pages") or [])}]</span> — {_esc(rf["detail"])}</div>'
            for rf in res.get("red_flags") or []
        )
        qs_html = "\n".join(
            f'<li>{_esc(q["question_tr"])} <span class="pno">[{", ".join(f"s. {p}" for p in q.get("pages") or [])}]</span></li>'
            for q in res.get("hkt_and_petition_questions") or []
        )
        en_details = ""
        if res.get("executive_summary_en"):
            en_details = (
                f'<details style="margin-top:8px;font-size:0.86rem;color:var(--muted);">'
                f'<summary style="cursor:pointer;">English summary</summary>'
                f'<p style="margin:6px 0 0;">{_esc(res["executive_summary_en"])}</p></details>'
            )
        llm_block = f"""
  <h2>Yapay Zeka Destekli Bilimsel Ön Değerlendirme <span class="badge">{_esc(llm.get('model'))}</span></h2>
  <p class="sub">PDF içinden seçilen {len(llm.get('pages_sent') or [])} sayfadan ({_esc(pages_used)}) üretilmiştir. Tüm sayısal verileri resmi PDF'teki <code>[s. N]</code> sayfalarından doğrulayın.</p>
  <section class="card prio">
    <p><strong>Özet:</strong> {_esc(res['executive_summary_tr'])}</p>
    {en_details}
    <div class="badges" style="margin-top:10px;">
      <span class="badge">Saha çalışması: {_esc(TR_BASELINE_STATUS.get(ba['field_survey_status'], ba['field_survey_status']))}</span>
      <span class="badge">Mevsimsel örnekleme: {_esc(TR_BASELINE_STATUS.get(ba['seasonal_sampling_status'], ba['seasonal_sampling_status']))}</span>
      <span class="badge">Kümülatif etki: {_esc(TR_BASELINE_STATUS.get(ba['cumulative_impact_status'], ba['cumulative_impact_status']))}</span>
    </div>
    <p class="detail" style="margin-top:10px;"><strong>Zeytinlik ve Korunan Alanlar:</strong> {_esc(ba['olive_and_protected_status'])}<br/>{_esc(ba['explanation'])}</p>
  </section>
  {f'<h3>Öne Çıkan Sayısal Bulgular</h3><table class="kv">{facts_html}</table>' if facts_html else ''}
  {f'<h3>Bilimsel ve Metodolojik Uyarılar</h3><section class="card">{flags_html}</section>' if flags_html else ''}
  {f'<h3>HKT ve İYUK 20/A İçin Taslak Teknik Sorular</h3><ul>{qs_html}</ul>' if qs_html else ''}
  <p class="sub"><em>Kapsam sınırları:</em> {_esc(res.get('data_limitations', ''))}</p>
"""

    return f"""<!doctype html>
<html lang="tr">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>e-ÇED Ön Özet #{_esc(filing_id)} — {_esc(filing['district'])}</title>
  <style>{BASE_CSS}</style>
</head>
<body>
<div class="wrap">
  <header>
    <div style="font-size:0.85rem;margin-bottom:8px;"><a href="../index.html">← Ege e-ÇED İzleme listesine dön</a> · <a href="{_esc(raw_md_filename)}">Ham Markdown (.md)</a></div>
    <h1>e-ÇED Ön Özet #{_esc(filing_id)} — {_esc(filing['district'])} / {_esc(filing['province'])}</h1>
    <p class="sub">{_esc(filing['project_name'])}</p>
    <div class="badges" style="margin-top:10px;">
      <span class="badge">{_esc(filing['decision_type'])}</span>
      <span class="badge">{_esc(filing['project_type'])}</span>
      {clocks_html}
    </div>
  </header>

  <table class="kv">
    <tr><th>Proje Sahibi</th><td>{_esc(filing['project_owner'])}</td></tr>
    <tr><th>Hazırlayan Kuruluş</th><td>{_esc(doc_meta.get('consulting_firm') or '—')}</td></tr>
    <tr><th>Sektör / Alt Sektör</th><td>{_esc(filing['sector'])} / {_esc(filing['sub_sector'])}</td></tr>
    <tr><th>Duyuru Tarihi</th><td><code>{_esc(filing['announcement_date_tr'])}</code> (yükleme: <code>{_esc(doc_meta.get('submitted_at') or '—')}</code>)</td></tr>
    <tr><th>PDF Kapsamı</th><td>{pdf_info['bytes'] / 1024 / 1024:.2f} MB · {analysis['page_count']} sayfa ({analysis['text_pages']} metin / {analysis['scanned_or_blank_pages']} taranmış-görüntü) · SHA-256 <code>{_esc(pdf_info['sha256'][:16])}…</code></td></tr>
    <tr><th>Resmi Bağlantılar</th><td><a href="{_esc(doc_meta.get('portal_doc_url', ''))}" target="_blank" rel="noopener">e-ÇED Portal Kaydı</a> · <a href="{_esc(pdf_url)}" target="_blank" rel="noopener">Resmi PDF Dosyası</a></td></tr>
  </table>

  {llm_block}

  <h2>Resmi Duyuru Metni</h2>
  <blockquote>{_esc(filing.get('detail_text', ''))}</blockquote>

  <h2>Otomatik Metin Taraması (Deterministik)</h2>
  <table class="kv">{checks_html}</table>
  <p class="sub">OCR içermeyen taranmış harita ve ekler otomatik metin taramasına dahil değildir.</p>

  <h2>Sayfa Kaynaklı Çıkarılan Bulgular</h2>
  <div class="cards">{''.join(sig_blocks)}</div>

  <h2>Belge Bölüm Haritası</h2>
  <ul>{headings_html or '<li style="color:var(--muted)">Yapılandırılmış bölüm başlığı tespit edilemedi.</li>'}</ul>

  <div class="notice">
    Çevre, Şehircilik ve İklim Değişikliği Bakanlığı'nın kamuya açık <code>eced-duyuru.csb.gov.tr</code> portalından üretilen bilgilendirme amaçlı şeffaflık aracıdır. Tüm alıntılar 1 tabanlı PDF sayfa numarasıyla <code>[s. N]</code> gösterilir. Yasal süreler otomatik hesaplanır; kesin süre ve hukuki işlem için mutlaka avukat/hukukçu doğrulaması alın.
  </div>
</div>
</body>
</html>
"""


def build_rss(filings: list[dict[str, Any]], digests_index: set[str], site_url: str) -> str:
    rss = ET.Element("rss", version="2.0")
    channel = ET.SubElement(rss, "channel")
    ET.SubElement(channel, "title").text = "Ege e-ÇED İzleme (İzmir ve Manisa)"
    ET.SubElement(channel, "link").text = site_url
    ET.SubElement(channel, "description").text = (
        "İzmir ve Manisa (Gediz Havzası) için kamuya açık e-ÇED duyuruları, "
        "10 günlük askı ve 30 günlük İYUK 20/A yasal süre takibi ile sayfa kaynaklı PDF ön özetleri."
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
        prio_prefix = "[ÖNCELİKLİ] " if f.get("priority_district") else ""
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
            f"{c['kind']}: {c['deadline']} ({c['days_remaining']} gün kaldı)"
            if c.get("deadline")
            else c["kind"]
            for c in f.get("statutory_clocks") or []
        )
        desc_parts = [
            f"Proje Sahibi: {f.get('project_owner', '')}",
            f"Sektör: {f.get('sector', '')} / {f.get('sub_sector', '')} ({f.get('project_type', '')})",
            f"Yasal Süreler: {clocks_txt or '—'}",
            f"Resmi Kayıt: {portal_url}",
        ]
        if pdf_url:
            desc_parts.append(f"Resmi PDF: {pdf_url}")
        if filing_id and filing_id in digests_index:
            desc_parts.append(f"Sayfa Kaynaklı Ön Özet: digests/{filing_id}.html")
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
    llm_summaries: dict[str, dict[str, Any]] = {}
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
            if saved.get("llm_synthesis") and saved["llm_synthesis"].get("result"):
                llm_summaries[fid] = saved["llm_synthesis"]

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
            actions.append(f'<a href="digests/{_esc(fid)}.html"><strong>Sayfa Kaynaklı Ön Özet</strong></a>')
            actions.append(f'<a href="digests/{_esc(fid)}.md">Ham .md</a>')
        if portal_url:
            actions.append(f'<a href="{_esc(portal_url)}" target="_blank" rel="noopener">e-ÇED Kaydı #{_esc(fid)}</a>')
        if pdf_url:
            actions.append(f'<a href="{_esc(pdf_url)}" target="_blank" rel="noopener">Resmi PDF</a>')

        detail_short = (f.get("detail_text") or "")[:320]
        if len(f.get("detail_text") or "") > 320:
            detail_short += "…"

        llm_info = llm_summaries.get(fid)
        llm_badge = ""
        llm_preview = ""
        if llm_info:
            lres = llm_info["result"]
            high_flags = sum(1 for rf in lres.get("red_flags") or [] if rf.get("severity") == "high")
            total_flags = len(lres.get("red_flags") or [])
            if high_flags:
                llm_badge = f'<span class="badge urgent">YZ İnceleme · {high_flags} yüksek / {total_flags} uyarı</span>'
            else:
                llm_badge = f'<span class="badge ok">YZ İnceleme · {total_flags} uyarı</span>'
            llm_preview = (
                f'<div class="detail" style="color:var(--text);">'
                f'<strong>Özet:</strong> {_esc(lres.get("executive_summary_tr", ""))}</div>'
            )

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
    {'<span class="badge ok">Öncelikli Koridor</span>' if prio else ''}
    <span class="badge">{_esc(f.get('decision_type', ''))}</span>
    <span class="badge">{_esc(f.get('project_type', ''))}</span>
    <span class="badge muted">{_esc(f.get('sector', ''))}</span>
    {_clock_badge_html(clock)}
    {llm_badge}
  </div>
  {llm_preview}
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
  <title>Ege e-ÇED İzleme</title>
  <link rel="alternate" type="application/rss+xml" title="Ege e-ÇED İzleme RSS" href="feed.xml" />
  <style>{BASE_CSS}</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>Ege e-ÇED İzleme</h1>
    <p class="sub">İzmir ve Manisa (Gediz Havzası) için kamuya açık e-ÇED duyuru takibi, yasal süre sayacı (10 günlük askı ve 30 günlük İYUK 20/A) ve sayfa kaynaklı PDF ön özetleri.</p>
    <div class="meta-bar">
      <span>Son güncelleme: <code>{_esc(built_at)}</code></span>
      <span><a href="feed.xml">RSS 2.0 Akışı (feed.xml)</a></span>
      <span>Resmi kaynak: <a href="https://eced-duyuru.csb.gov.tr/eced-prod/duyurular.xhtml" target="_blank" rel="noopener">eced-duyuru.csb.gov.tr</a></span>
    </div>
  </header>

  <section class="stats">
    <div class="stat"><div class="num">{total}</div><div class="lbl">Takip Edilen Dosya</div></div>
    <div class="stat"><div class="num">{prio_count}</div><div class="lbl">Öncelikli Koridor</div></div>
    <div class="stat"><div class="num">{active_count}</div><div class="lbl">Aktif Yasal Süre</div></div>
    <div class="stat"><div class="num">{digested_count}</div><div class="lbl">Sayfa Kaynaklı Ön Özet</div></div>
  </section>

  <section class="controls">
    <input id="q" type="search" placeholder="İlçe, proje adı, şirket, sektör veya dosya no ara…" />
    <button class="pill active" data-filter="all">Tümü</button>
    <button class="pill" data-filter="prio">Öncelikli Koridor</button>
    <button class="pill" data-filter="active">Aktif Süreler</button>
    <button class="pill" data-filter="digest">Ön Özetli</button>
    <button class="pill" data-filter="ek1">Yalnızca Ek-1</button>
    {prov_buttons}
  </section>

  <div id="count" class="sub" style="margin-bottom:10px;">Toplam {total} dosya gösteriliyor</div>
  <main class="cards" id="cards">
    {''.join(cards_html)}
  </main>

  <div class="notice">
    <strong>Yalnızca bilgilendirme amaçlıdır:</strong> Tüm kayıtlar T.C. Çevre, Şehircilik ve İklim Değişikliği Bakanlığı'nın kamuya açık e-ÇED duyuru portalından alınır. 2577 sayılı İYUK Madde 20/A uyarınca ÇED kararlarına karşı iptal davası açma süresi <strong>30 gündür</strong> ve <em>İYUK Madde 11 başvuruları bu süreyi durdurmaz</em>. Kesin tarih ve hukuki süreçler için mutlaka yetkili hukukçulara danışın.
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
    countEl.textContent = `${{cards.length}} dosyadan ${{shown}} tanesi gösteriliyor`;
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

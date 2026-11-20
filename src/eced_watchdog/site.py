"""Static HTML dashboard with interactive Türkiye Leaflet map, per-filing digests, Turkish guide, and RSS 2.0 feed."""

from __future__ import annotations

import html
import json
import shutil
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from .geo import province_centroid

LEAFLET_CSS = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
LEAFLET_JS = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"

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
  line-height: 1.6;
}
.wrap { max-width: 1240px; margin: 0 auto; padding: 24px 18px 64px; }
a { color: var(--accent); text-decoration: none; }
a:hover { text-decoration: underline; }
header { border-bottom: 1px solid var(--border); padding-bottom: 16px; margin-bottom: 20px; }
h1 { margin: 0 0 6px; font-size: 1.55rem; }
h2 { margin: 26px 0 10px; font-size: 1.2rem; }
h3 { margin: 16px 0 8px; font-size: 1rem; }
.sub { color: var(--muted); font-size: 0.92rem; margin: 0; }
.meta-bar { display: flex; flex-wrap: wrap; gap: 14px; margin-top: 12px; font-size: 0.85rem; color: var(--muted); }
.stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 10px; margin: 16px 0 18px; }
.stat { background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 12px 14px; }
.stat .num { font-size: 1.45rem; font-weight: 700; }
.stat .lbl { font-size: 0.78rem; color: var(--muted); }
.map-box {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  overflow: hidden;
  margin-bottom: 18px;
}
#map { width: 100%; height: 420px; background: var(--badge-bg); }
#digest-map { width: 100%; height: 320px; background: var(--badge-bg); }
.map-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
  padding: 9px 14px;
  font-size: 0.8rem;
  color: var(--muted);
  border-top: 1px solid var(--border);
}
.dot { display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 5px; vertical-align: middle; }
.controls { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-bottom: 16px; }
input[type="search"], select.filter-select {
  padding: 8px 12px;
  border-radius: 6px;
  border: 1px solid var(--border);
  background: var(--surface);
  color: var(--text);
  font-size: 0.9rem;
}
input[type="search"] { flex: 1 1 240px; }
select.filter-select { min-width: 170px; }
button.pill {
  padding: 7px 12px;
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
  padding: 15px 17px;
}
.card.ek1 { border-left: 4px solid var(--accent); }
.row-top { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 8px; align-items: baseline; }
.title { font-weight: 600; font-size: 0.98rem; }
.badges { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 7px; }
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
.detail { font-size: 0.87rem; color: var(--muted); margin: 8px 0; }
.actions { display: flex; flex-wrap: wrap; gap: 12px; font-size: 0.84rem; margin-top: 8px; }
.notice {
  margin-top: 28px;
  padding: 14px 16px;
  border: 1px solid var(--border);
  border-radius: 8px;
  font-size: 0.84rem;
  color: var(--muted);
}
table.kv { width: 100%; border-collapse: collapse; margin: 12px 0; font-size: 0.9rem; }
table.kv th, table.kv td { border: 1px solid var(--border); padding: 8px 11px; text-align: left; vertical-align: top; }
table.kv th { width: 240px; background: var(--badge-bg); }
code { background: var(--badge-bg); padding: 1px 5px; border-radius: 4px; font-size: 0.85em; }
blockquote { margin: 10px 0; padding: 11px 15px; border-left: 3px solid var(--accent); background: var(--surface); font-size: 0.9rem; }
.hit { margin: 7px 0; font-size: 0.88rem; }
.pno { font-weight: 700; color: var(--accent); }
.leaflet-popup-content { color: #1f2328; font-size: 0.85rem; line-height: 1.45; }
"""

TR_SIGNAL_LABELS = {
    "coordinates_and_footprint": "Koordinatlar, Parsel ve Alan Büyüklüğü",
    "water_and_discharge": "Su Kullanımı, Hidrojeoloji ve Deşarj",
    "protected_land_and_olive": "Korunan Alanlar, Orman ve Zeytinlikler",
    "ecology_and_baseline": "Flora, Fauna ve Saha Metodolojisi",
    "pollutants_and_hazards": "Emisyonlar, Jeokimya ve Atıklar",
    "cost_and_capacity": "Proje Bedeli, Güç ve Kapasite",
    "splitting_and_thresholds": "Proje Parçalama, Kapasite Artışı ve Eşik Değerler",
}

TR_DANISTAY_CATEGORIES = {
    "zeytinlik_3573": "3573 Zeytincilik (3 km)",
    "proje_parcalama": "Proje Parçalama / Eşik Değer",
    "kumulatif_etki": "Kümülatif Etki",
    "flora_fauna_mevsimsel": "Flora / Fauna & Mevsimsellik",
    "su_hidrojeoloji": "Su / Hidrojeoloji",
    "tarim_orman_korunan_alan": "5403 / Orman / Korunan Alan",
    "izleme_olcum_celiskisi": "Ölçüm / İç Tutarlılık",
}

TR_BASELINE_STATUS = {
    "field_survey_documented": "Belgelenmiş saha çalışması mevcut",
    "literature_only": "Yalnızca literatür taramasına dayalı",
    "mixed_or_unclear": "Karışık veya yöntemi belirsiz",
    "not_found": "İncelenen sayfalarda tespit edilemedi",
    "completed_pre_project": "Başvuru öncesinde tamamlanmış",
    "promised_post_approval_only": "Yalnızca onay sonrasına ertelenmiş",
    "unclear": "Belirsiz",
    "quantitatively_assessed": "Nicel değerlendirme yapılmış",
    "superficial_or_boilerplate": "Yüzeysel veya şablon düzeyinde",
    "omitted_or_not_found": "Eksik veya tespit edilemedi",
}

TR_SEVERITY = {
    "high": "YÜKSEK",
    "medium": "ORTA",
    "low": "DÜŞÜK",
}


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
    if code == "process_open":
        return '<span class="badge">Karar Öncesi İnceleme Sürecinde (m. 8/16)</span>'
    label = {
        "iyuk_20a": "İYUK 20/A (30g)",
        "aski_10d": "Madde 14 Askı (10g)",
        "hkt": "HKT Toplantısı",
        "idk": "İDK İncelemesi",
    }.get(code, "Yasal Süre")
    if dr is None:
        return f'<span class="badge warn">{_esc(label)} · Tarih duyuru metnindedir</span>'
    if dr < 0:
        return f'<span class="badge muted">{_esc(label)} · Süresi doldu ({clock["deadline"]})</span>'
    if dr <= 7:
        return f'<span class="badge urgent">{_esc(label)} · {dr} gün kaldı ({clock["deadline"]})</span>'
    if dr <= 15:
        return f'<span class="badge warn">{_esc(label)} · {dr} gün kaldı ({clock["deadline"]})</span>'
    return f'<span class="badge ok">{_esc(label)} · {dr} gün kaldı ({clock["deadline"]})</span>'


def _marker_color(filing: dict[str, Any], has_digest: bool) -> str:
    clock = _best_active_clock(filing)
    if clock:
        code = clock.get("code", "")
        dr = clock.get("days_remaining")
        if code == "process_open":
            return "#58a6ff"  # early warning / review in progress
        if dr is not None:
            if 0 <= dr <= 7:
                return "#f85149"  # urgent red
            if 8 <= dr <= 15:
                return "#d29922"  # amber
            if dr > 15:
                return "#3fb950"  # green active
            return "#6e7681"  # expired
        return "#d29922"  # undated HKT/İDK
    if filing.get("project_type") == "Ek-1" or has_digest:
        return "#58a6ff"
    return "#6e7681"


def render_digest_html(saved: dict[str, Any], raw_md_filename: str) -> str:
    filing = saved["filing"]
    docs = filing.get("documents") or [{}]
    doc_meta = docs[0]
    pdf_info = saved["pdf_info"]
    analysis = saved["analysis"]
    filing_id = doc_meta.get("filing_id") or "bilinmiyor"
    pdf_url = doc_meta["pdf_urls"][0]["url"] if doc_meta.get("pdf_urls") else ""

    geo = analysis.get("geo") or {}
    if geo.get("lat") and geo.get("lon"):
        g_lat, g_lon = geo["lat"], geo["lon"]
        g_prec = geo.get("precision", "province_centroid")
        g_pts = geo.get("points") or []
    else:
        g_lat, g_lon = province_centroid(filing.get("province", ""))
        g_prec = "province_centroid"
        g_pts = []

    geo_caption = (
        f"PDF metninden çıkarılan kesin proje koordinatları ({geo.get('point_count', len(g_pts))} nokta, "
        f"datum: {geo.get('datum') or 'WGS84'}, sayfa: {', '.join(f's.{p}' for p in (geo.get('pages') or [])[:6])})."
        if g_prec == "exact_pdf"
        else "PDF dosyasında metin olarak okunabilir koordinat tablosu tespit edilemediği için il merkezi yaklaşık konum olarak gösterilmektedir."
    )
    zoom_lvl = 12 if g_prec == "exact_pdf" else 8
    osm_url = f"https://www.openstreetmap.org/?mlat={g_lat}&mlon={g_lon}#map={zoom_lvl}/{g_lat}/{g_lon}"
    gmaps_url = f"https://www.google.com/maps/search/?api=1&query={g_lat},{g_lon}"

    checks = analysis["audit_checks"]
    check_rows = [
        ("Saha veya arazi çalışması ifadesi", checks["mentions_field_survey"]),
        ("Literatür taraması ifadesi", checks["mentions_literature_only_cue"]),
        ("Mevsimsel örnekleme ifadesi", checks["mentions_seasonal_sampling"]),
        ("Kümülatif etki değerlendirmesi ifadesi", checks["mentions_cumulative_impact"]),
        ("3573 sayılı Zeytincilik Kanunu veya zeytinlik ifadesi", checks["mentions_olive_law_3573"]),
        ("Yeraltı suyu, akifer veya hidrojeoloji ifadesi", checks["mentions_groundwater_or_aquifer"]),
        ("Endemik tür, IUCN veya Bern Sözleşmesi ifadesi", checks["mentions_iucn_or_endemic"]),
    ]
    checks_html = "\n".join(
        f"<tr><th>{_esc(lbl)}</th><td>"
        + ('<span class="badge ok">Metinde yer almaktadır</span>' if ok else '<span class="badge urgent">Metinde tespit edilemedi; doğrudan PDF üzerinden kontrol ediniz</span>')
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
        ) or '<div class="hit" style="color:var(--muted)">İlgili başlık altında metin eşleşmesi bulunamamıştır.</div>'
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
            + (
                f'<span class="badge">{_esc(TR_DANISTAY_CATEGORIES.get(rf["category"], rf["category"]))}</span> '
                if rf.get("category")
                else ""
            )
            + f'<strong>{_esc(rf["title"])}</strong> '
            f'<span class="pno">[{", ".join(f"s. {p}" for p in rf.get("pages") or [])}]</span> — {_esc(rf["detail"])}</div>'
            for rf in res.get("red_flags") or []
        )
        bilirkisi = res.get("recommended_bilirkisi_disciplines") or []
        bilirkisi_html = ""
        if bilirkisi:
            pills_b = " ".join(f'<span class="badge">{_esc(d)}</span>' for d in bilirkisi)
            bilirkisi_html = (
                f'<h3>Keşif ve Bilirkişi Heyeti İçin Önerilen Uzmanlık Alanları</h3>'
                f'<section class="card"><div class="badges">{pills_b}</div>'
                f'<p class="detail" style="margin-top:8px;">Danıştay içtihatları uyarınca bilirkişi heyetinin tek sayıda uzmandan oluşması, proje niteliğine uygun tüm disiplinleri içermesi ve plan kararlarıyla ilişkili davalarda Şehir ve Bölge Plancısına yer verilmesi gerekmektedir.</p></section>'
            )
        qs_html = "\n".join(
            f'<li>{_esc(q["question_tr"])} <span class="pno">[{", ".join(f"s. {p}" for p in q.get("pages") or [])}]</span></li>'
            for q in res.get("hkt_and_petition_questions") or []
        )
        en_details = ""
        if res.get("executive_summary_en"):
            en_details = (
                f'<details style="margin-top:8px;font-size:0.86rem;color:var(--muted);">'
                f'<summary style="cursor:pointer;">İngilizce özet (English summary)</summary>'
                f'<p style="margin:6px 0 0;">{_esc(res["executive_summary_en"])}</p></details>'
            )
        llm_block = f"""
  <h2>Yapay Zeka Destekli Bilimsel Ön Değerlendirme <span class="badge">{_esc(llm.get('model'))}</span></h2>
  <p class="sub">Bu değerlendirme, resmi PDF dosyasından seçilen {len(llm.get('pages_sent') or [])} sayfa ({_esc(pages_used)}) esas alınarak hazırlanmıştır. Tüm sayısal verilerin ve tespitlerin resmi PDF belgesindeki ilgili <code>[s. N]</code> sayfalarından doğrulanması gerekir.</p>
  <section class="card ek1">
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
  {f'<h3>Danıştay Ölçütlerine Göre Bilimsel ve Hukuki Bulgular</h3><section class="card">{flags_html}</section>' if flags_html else ''}
  {bilirkisi_html}
  {f'<h3>HKT Tutanakları ve Bilirkişi İncelemesi İçin Taslak Teknik Sorular</h3><ul>{qs_html}</ul>' if qs_html else ''}
  <p class="sub"><em>İnceleme sınırları:</em> {_esc(res.get('data_limitations', ''))}</p>
"""

    map_payload = json.dumps(
        {
            "lat": g_lat,
            "lon": g_lon,
            "zoom": zoom_lvl,
            "precision": g_prec,
            "points": g_pts,
            "label": f"{filing['province']} / {filing['district']} — {filing['project_name'][:90]}",
        },
        ensure_ascii=False,
    )

    return f"""<!doctype html>
<html lang="tr">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>e-ÇED Ön Özet #{_esc(filing_id)} — {_esc(filing['province'])} / {_esc(filing['district'])}</title>
  <link rel="stylesheet" href="{LEAFLET_CSS}" />
  <style>{BASE_CSS}</style>
</head>
<body>
<div class="wrap">
  <header>
    <div style="font-size:0.85rem;margin-bottom:8px;"><a href="../index.html">← Türkiye e-ÇED İzleme listesine dön</a> · <a href="../rehber.html">Kullanım ve İnceleme Rehberi</a> · <a href="{_esc(raw_md_filename)}">Ham Markdown (.md)</a></div>
    <h1>e-ÇED Ön Özet #{_esc(filing_id)} — {_esc(filing['province'])} / {_esc(filing['district'])}</h1>
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
    <tr><th>Duyuru Tarihi</th><td><code>{_esc(filing['announcement_date_tr'])}</code> (belge yükleme tarihi: <code>{_esc(doc_meta.get('submitted_at') or '—')}</code>)</td></tr>
    <tr><th>PDF Kapsamı</th><td>{pdf_info['bytes'] / 1024 / 1024:.2f} MB · {analysis['page_count']} sayfa ({analysis['text_pages']} metin sayfası / {analysis['scanned_or_blank_pages']} taranmış veya görüntü sayfası) · SHA-256 <code>{_esc(pdf_info['sha256'][:16])}…</code></td></tr>
    <tr><th>Resmi Bağlantılar</th><td><a href="{_esc(doc_meta.get('portal_doc_url', ''))}" target="_blank" rel="noopener">e-ÇED Portal Kaydı</a> · <a href="{_esc(pdf_url)}" target="_blank" rel="noopener">Resmi PDF Dosyası</a> · <a href="{_esc(osm_url)}" target="_blank" rel="noopener">OpenStreetMap</a> · <a href="{_esc(gmaps_url)}" target="_blank" rel="noopener">Google Haritalar</a></td></tr>
  </table>

  <h2>Konum Haritası</h2>
  <div class="map-box">
    <div id="digest-map"></div>
    <div class="map-legend"><span>{_esc(geo_caption)}</span></div>
  </div>

  {llm_block}

  <h2>Resmi Duyuru Metni</h2>
  <blockquote>{_esc(filing.get('detail_text', ''))}</blockquote>

  <h2>Otomatik Metin Taraması (Deterministik)</h2>
  <table class="kv">{checks_html}</table>
  <p class="sub">Metin katmanı (OCR) bulunmayan taranmış harita ve kurum görüşü ekleri otomatik metin taramasına dahil edilmemiştir.</p>

  <h2>Sayfa Kaynaklı Çıkarılan Bulgular</h2>
  <div class="cards">{''.join(sig_blocks)}</div>

  <h2>Belge Bölüm Haritası</h2>
  <ul>{headings_html or '<li style="color:var(--muted)">Belge içinde yapılandırılmış bölüm başlığı tespit edilememiştir.</li>'}</ul>

  <div class="notice">
    Bu sayfa, T.C. Çevre, Şehircilik ve İklim Değişikliği Bakanlığı'nın kamuya açık <code>eced-duyuru.csb.gov.tr</code> duyuru portalındaki kayıtlar esas alınarak bilgilendirme amacıyla hazırlanmıştır. Alıntıların tamamı 1 tabanlı PDF sayfa numarasıyla (<code>[s. N]</code>) gösterilmektedir. Yasal süreler otomatik olarak hesaplanır; kesin sürelerin ve hukuki başvuru yollarının yetkili hukukçular tarafından teyit edilmesi gerekir.
  </div>
</div>
<script src="{LEAFLET_JS}"></script>
<script>
(() => {{
  if (typeof L === 'undefined') return;
  const g = {map_payload};
  const map = L.map('digest-map').setView([g.lat, g.lon], g.zoom);
  L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
    maxZoom: 18,
    attribution: '&copy; OpenStreetMap katkıda bulunanları'
  }}).addTo(map);
  if (g.precision === 'exact_pdf' && g.points.length > 1) {{
    const latlngs = g.points.map(p => [p[0], p[1]]);
    const poly = L.polyline(latlngs, {{ color: '#58a6ff', weight: 3, opacity: 0.85 }}).addTo(map);
    for (const ll of latlngs.slice(0, 30)) {{
      L.circleMarker(ll, {{ radius: 4, color: '#ffffff', fillColor: '#f85149', fillOpacity: 0.9, weight: 1 }}).addTo(map);
    }}
    map.fitBounds(poly.getBounds().pad(0.25));
  }} else {{
    L.circleMarker([g.lat, g.lon], {{
      radius: g.precision === 'exact_pdf' ? 8 : 11,
      color: '#ffffff',
      fillColor: g.precision === 'exact_pdf' ? '#f85149' : '#58a6ff',
      fillOpacity: g.precision === 'exact_pdf' ? 0.9 : 0.45,
      weight: 2
    }}).bindPopup(g.label).addTo(map).openPopup();
  }}
}})();
</script>
</body>
</html>
"""


def build_rss(filings: list[dict[str, Any]], digests_index: set[str], site_url: str) -> str:
    rss = ET.Element("rss", version="2.0")
    channel = ET.SubElement(rss, "channel")
    ET.SubElement(channel, "title").text = "Türkiye e-ÇED İzleme Platformu"
    ET.SubElement(channel, "link").text = site_url
    ET.SubElement(channel, "description").text = (
        "T.C. Çevre, Şehircilik ve İklim Değişikliği Bakanlığı'nın 81 ildeki kamuya açık e-ÇED duyuruları, "
        "10 günlük askı ve 30 günlük İYUK Madde 20/A süre takibi ile sayfa kaynaklı teknik ön özetler."
    )
    ET.SubElement(channel, "language").text = "tr"
    ET.SubElement(channel, "lastBuildDate").text = format_datetime(datetime.now(timezone.utc))

    for f in filings[:80]:
        docs = f.get("documents") or []
        doc_meta = docs[0] if docs else {}
        filing_id = doc_meta.get("filing_id")
        portal_url = doc_meta.get("portal_doc_url") or "https://eced-duyuru.csb.gov.tr/eced-prod/duyurular.xhtml"
        pdf_url = doc_meta["pdf_urls"][0]["url"] if doc_meta.get("pdf_urls") else None

        item = ET.SubElement(channel, "item")
        ET.SubElement(item, "title").text = (
            f"[{f['province']}/{f['district']}] {f['decision_type']} ({f['project_type']}) — {f['project_name']}"
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
            f"Yasal Süreler: {clocks_txt or 'Belirtilmemiş'}",
            f"Resmi Kayıt: {portal_url}",
        ]
        if pdf_url:
            desc_parts.append(f"Resmi PDF: {pdf_url}")
        if filing_id and filing_id in digests_index:
            desc_parts.append(f"Sayfa Kaynaklı Ön Özet: {site_url.rstrip('/')}/digests/{filing_id}.html")
        if f.get("detail_text"):
            desc_parts.append("")
            desc_parts.append(f["detail_text"])
        ET.SubElement(item, "description").text = "\n".join(desc_parts)

    ET.indent(rss, space="  ")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(rss, encoding="unicode")


def render_guide_html() -> str:
    template_text = """# Teknik İnceleme Notu — e-ÇED #[DOSYA_NO] ([İL] / [İLÇE])

- Resmi e-ÇED Kaydı: [e-ÇED portal bağlantısı]
- Aşama ve Yasal Son Tarih: [10 günlük askı süresi / HKT tarihi / 30 günlük İYUK Madde 20/A son günü]

1. Başlangıç Verisi ve Örnekleme Eksiklikleri ([s. N]):
   - Raporda saha çalışması tarihleri, mevsimsel tekrar durumu veya örnekleme yöntemine ilişkin tespit edilen eksiklikleri sayfa numarasıyla belirtiniz.

2. Ekolojik, Hidrolojik veya Jeokimyasal Çelişkiler ([s. N]):
   - Su kaynakları, denizel/karasal ekosistemler, atık yönetimi veya emisyon varsayımlarındaki bilimsel tutarsızlıkları sayfa numarasıyla özetleyiniz.

3. Kümülatif Bölgesel Etki ve Mevzuat Boşlukları ([s. N]):
   - Çevredeki mevcut tesislerle birlikte ortaya çıkacak birikimli etkiler ile 3573 sayılı Zeytincilik Kanunu, 5403 sayılı Toprak Koruma Kanunu veya korunan alan statüsüne ilişkin eksiklikleri yazınız.

4. HKT Tutanağı veya İdari Başvuru İçin Taslak Teknik Sorular:
   - [Somut, tarafsız ve ölçülebilir teknik soru 1] ([s. N])
   - [Somut, tarafsız ve ölçülebilir teknik soru 2] ([s. N])
   - [Somut, tarafsız ve ölçülebilir teknik soru 3] ([s. N])

5. İletilmesi Önerilen Kurum ve Paydaşlar:
   - İlgili İl Barosu Çevre ve Kent Hukuku Komisyonu / TMMOB İl Koordinasyon Kurulu / Yerel Çevre Platformu / Belediye Çevre Birimi / Yerel Basın"""

    return f"""<!doctype html>
<html lang="tr">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>Kullanım ve Bilimsel İnceleme Rehberi — Türkiye e-ÇED İzleme Platformu</title>
  <style>
{BASE_CSS}
pre {{
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 15px 17px;
  overflow-x: auto;
  font-size: 0.85rem;
  line-height: 1.55;
  white-space: pre-wrap;
}}
.step-grid {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
  gap: 12px;
  margin: 14px 0 22px;
}}
.step-num {{
  display: inline-block;
  font-size: 0.75rem;
  font-weight: 700;
  color: var(--accent);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  margin-bottom: 4px;
}}
  </style>
</head>
<body>
<div class="wrap">
  <header>
    <div style="font-size:0.85rem;margin-bottom:8px;"><a href="index.html">← Türkiye e-ÇED İzleme listesine dön</a> · <a href="feed.xml">RSS 2.0 Akışı</a></div>
    <h1>Platformun Amacı ve Bilimsel İnceleme Rehberi</h1>
    <p class="sub">Çevre bilimciler, ekologlar, mühendisler, hukukçular, yerel gazeteciler ve yurttaşlar için sayfa kaynaklı ÇED inceleme kılavuzu.</p>
  </header>

  <section class="card ek1">
    <h2 style="margin-top:0;">1. Hukuki Süreç, Gerçek Süreler ve Nihai Amaç</h2>
    <p>T.C. Çevre, Şehircilik ve İklim Değişikliği Bakanlığı, Türkiye genelindeki tüm Çevresel Etki Değerlendirmesi (ÇED) başvurularını, Halkın Katılımı Toplantısı (HKT) ilanlarını, İnceleme Değerlendirme Komisyonu (İDK) toplantılarını ve nihai kararları kamuya açık biçimde yayımlamaktadır. 29 Temmuz 2022 tarihli ve 31907 sayılı Resmî Gazete'de yayımlanan ÇED Yönetmeliği ile 2025–2026 dönemindeki güncellemeler uyarınca (Ek-2 projelerinde eski <em>"ÇED Gerekli Değildir"</em> ifadesi yerini <strong>"ÇED Olumlu (Kapsam Ek-2)"</strong> kararına bırakmıştır) izlenmesi gereken temel yasal aşamalar şunlardır:</p>
    <ul>
      <li><strong>İYUK Madde 20/A İptal Davası Süresi (30 Takvim Günü):</strong> <em>ÇED Olumlu</em>, <em>ÇED Olumlu (Kapsam Ek-2)</em> veya <em>ÇED Gerekli Değildir</em> kararlarına karşı açılacak iptal davaları 2577 sayılı İdari Yargılama Usulü Kanunu'nun <strong>20/A maddesi</strong> uyarınca ivedi yargılama usulüne tabidir. Dava açma süresi kararın ilanı veya tebliğinden itibaren <strong>30 takvim günüdür</strong> ve idareye yapılan <strong>İYUK Madde 11 başvuruları bu süreyi durdurmaz</strong>.</li>
      <li><strong>Madde 14 Nihai ÇED Askı Süresi (10 Takvim Günü):</strong> İDK tarafından son şekli verilen Ek-1 kapsamındaki Nihai ÇED Raporu, halkın görüş ve önerilerini almak üzere <strong>10 takvim günü</strong> süreyle askıda ve internette ilan edilir.</li>
      <li><strong>HKT (m. 9), İDK (m. 11–12) ve Karar Öncesi Süreç (m. 8 / m. 16):</strong> <em>ÇED Süreci Başlayan</em> ilanları kesin bir 10 günlük son tarih doğurmaz; karar verilmeden önce yazılı görüş sunulabilecek ve dosya takip edilebilecek erken uyarı aşamasıdır.</li>
    </ul>
    <p><strong>Bu platformun nihai amacı</strong>, polemik üretmek değil; yüzlerce sayfalık resmi PDF dosyalarındaki bilimsel ve hukuki eksiklikleri sayfa numaralarıyla (<code>[s. N]</code>) görünür kılarak, dava ehliyeti bulunan yerel aktörlerin ve uzmanların yasal süreler dolmadan <strong>keşif ve bilirkişi incelemesine esas olacak teknik dayanakları</strong> hazırlamasına yardımcı olmaktır.</p>
  </section>

  <h2>2. İdari Yargıda Ne "Bulgu" Sayılır? (7 Temel Danıştay İptal Ölçütü)</h2>
  <p class="sub">Türk idari yargısında ÇED iptal davaları büyük ölçüde mahallinde yapılan <strong>keşif ve çok disiplinli bilirkişi heyeti raporu</strong> üzerinden karara bağlanır. Danıştay'ın yerleşik içtihatlarına göre bir raporun hukuka aykırı bulunmasına doğrudan yol açan temel bulgu kategorileri şunlardır:</p>
  <table class="kv">
    <tr><th>1. 3573 Sayılı Zeytincilik Kanunu (m. 20)</th><td>Zeytinlik sahaları içinde ve bu sahalara <strong>en az 3 kilometre mesafede</strong> zeytinyağı fabrikası hariç toz, duman veya kimyevi atık bırakan tesislerin kurulması mutlak olarak yasaktır. Danıştay içtihatları uyarınca raporda verilen filtreleme veya toz önleme taahhütleri bu kanuni yasağı ortadan kaldırmaz.</td></tr>
    <tr><th>2. Proje Parçalama (Eşik Değer Dolanılması)</th><td>Esasen Ek-1 kapsamına girmesi gereken bir yatırımın, ruhsat sahasının veya kapasite artışının yapay biçimde bölünerek Ek-2 üzerinden geçirilmeye çalışılması Danıştay tarafından kanuna karşı hile ve bütüncül inceleme ilkesine aykırılık sayılarak iptal edilmektedir.</td></tr>
    <tr><th>3. Kümülatif (Birikimli) Etki Eksikliği</th><td>Projenin bölgedeki mevcut veya planlanan diğer maden, enerji, sanayi ve su kullanım yükleriyle birlikte oluşturacağı birikimli ekolojik etkinin ve ekosistem taşıma kapasitesinin değerlendirilmemesi başlıca iptal gerekçelerindendir.</td></tr>
    <tr><th>4. Flora, Fauna ve Mevsimsellik Eksikliği</th><td>Yalnızca literatür taramasına (<code>L</code>) veya tek günlük/tek mevsimlik gözlemlere dayanan tür listeleri, göçmen kuşların ve endemik/IUCN/Bern türlerinin tespit edilmemesi ile orman ekosisteminin bilimsel dayanaktan yoksun "rehabilitasyon" vaatleriyle yok edilmesi raporları sakatlar.</td></tr>
    <tr><th>5. Su Kaynakları ve Başlangıç Analizleri</th><td>Yeraltı suyu, akifer, dere rejimi, içme suyu havzası veya can suyu etkilerinin hidrojeolojik olarak modellenmemesi ya da DSİ gibi kurumların talep ettiği faaliyet öncesi başlangıç su analizlerinin onay sonrasına ertelenmesi ağır metodolojik eksikliktir.</td></tr>
    <tr><th>6. 5403 Toprak Koruma, Orman, ÖÇK/SİT ve Kurum Görüşleri</th><td>Mutlak veya dikili tarım arazilerinin vasfının bozulması, zorunlu kurum görüşlerinin (DSİ, İl Tarım, OGM, Kültür Varlıkları) eksik olması ya da yer/teknoloji alternatiflerinin hiç irdelenmemesi hukuka aykırılık doğurur.</td></tr>
    <tr><th>7. Ölçüm Hataları ve Bilirkişi Denetimi</th><td>İç tutarsızlıklar (kapasite, koordinat veya parsel çelişkileri) ile teknik olarak imkânsız izleme yöntemleri (örneğin akustik gürültü için yalnızca "görsel takip" taahhüt edilmesi) keşif ve bilirkişi aşamasında doğrudan denetim konusu yapılır.</td></tr>
  </table>

  <h2>3. Kimler Dava Açabilir? (Dava Ehliyeti ve Danıştay İçtihatları)</h2>
  <p class="sub">2577 sayılı İYUK Madde 2 uyarınca iptal davası açabilmek için işlem ile davacı arasında <strong>meşru, kişisel ve güncel bir menfaat bağı</strong> bulunması zorunludur. Yanlış davacı seçimi davanın daha ilk incelemede <em>ehliyet yönünden reddine</em> yol açar:</p>
  <table class="kv">
    <tr><th>Yöre Sakinleri ve Taşınmaz Sahipleri</th><td>Projenin etki alanında ikamet eden yurttaşlar, komşular ve bölgede taşınmazı bulunan kişiler en güçlü ve yerleşik dava ehliyetine sahiptir.</td></tr>
    <tr><th>TMMOB ve İlgili Meslek Odaları</th><td>Çevre, Ziraat, Jeoloji, Orman, Maden ve Şehir Plancıları Odaları gibi kamu kurumu niteliğindeki meslek kuruluşları, kendi uzmanlık ve görev alanlarına giren projelerde doğrudan dava açma ehliyetine sahiptir.</td></tr>
    <tr><th>Çevre Dernekleri</th><td>Ana tüzüğünde açıkça çevre ve doğa koruma amacı yer alan ve projenin bulunduğu coğrafi bölgede faaliyet gösteren derneklerin dava ehliyeti kabul edilmektedir.</td></tr>
    <tr><th>İlgili Belediyeler</th><td>Proje sahasını veya etki alanını sınırları içinde barındıran büyükşehir ve ilçe belediyeleri idari yargıda dava açabilmektedir.</td></tr>
    <tr><th>Barolar (Önemli İçtihat Uyarısı)</th><td>Danıştay'ın güncel ve istikrarlı içtihatları, <strong>baroların kendi tüzel kişilikleri adına ÇED iptal davası açma ehliyetini çoğunlukla reddetmektedir</strong>. Bu nedenle il barolarının Çevre ve Kent Hukuku Komisyonları doğrudan davacı sıfatıyla değil; <strong>yöre sakinlerine hukuki danışmanlık, dilekçe hazırlığı ve avukatlık temsili sağlamak</strong> açısından kritik rol üstlenmektedir.</td></tr>
  </table>

  <h2>4. Uzmanlar İçin 4 Adımlı Çalışma Akışı (Ayda 1–2 Saat)</h2>
  <p class="sub">Bu sürece katkı sunmak için yeni bir dernek kurmanız, yazılım bilgisine sahip olmanız ya da platformu her gün izlemeniz gerekmez. Uzmanlık alanınızla örtüşen bir dosya yayımlandığında şu dört adımı izleyebilirsiniz:</p>

  <div class="step-grid">
    <div class="card">
      <div class="step-num">Adım 1 · Yaklaşık 5 dakika</div>
      <div class="title">Süresi Yaklaşan Dosyayı Seçiniz</div>
      <p class="detail">Ana sayfa varsayılan olarak <strong>en acil yasal süreye</strong> (30 günlük İYUK 20/A ve 10 günlük Madde 14 askı sürelerine) göre sıralanır. İl seçicisini kullanarak uzmanlık alanınıza giren tek bir dosyayı açınız.</p>
    </div>
    <div class="card">
      <div class="step-num">Adım 2 · 30–60 dakika</div>
      <div class="title">Bulguları Resmi PDF Üzerinden Doğrulayınız</div>
      <p class="detail">Ön özetteki Danıştay kategorili bulguları ve <code>[s. N]</code> sayfa numaralarını inceleyiniz. Doğrudan <strong>Resmi PDF Dosyası</strong> üzerindeki ilgili sayfaları açarak tespitleri kendi uzmanlık süzgecinizden geçiriniz.</p>
    </div>
    <div class="card">
      <div class="step-num">Adım 3 · Yaklaşık 30 dakika</div>
      <div class="title">Bir Sayfalık Teknik Not ve Bilirkişi Talebi Hazırlayınız</div>
      <p class="detail">Aşağıdaki şablonu doldurunuz. Yalnızca doğrulanmış sayfa numaralı olgulara dayanan somut teknik soruları ve keşif heyetinde bulunması gereken akademik uzmanlık alanlarını (örneğin mutlaka <em>Şehir ve Bölge Plancısı</em>, <em>Hidrojeolog</em>, <em>Biyolog</em>) belirtiniz.</p>
    </div>
    <div class="card">
      <div class="step-num">Adım 4 · Yaklaşık 5 dakika</div>
      <div class="title">Ehliyetli Aktörlere veya Hukukçulara İletiniz</div>
      <p class="detail">Hazırladığınız teknik notu ilgili TMMOB odasına, bölgedeki çevre derneğine, belediye çevre birimine veya yöre sakinlerini temsil eden çevre hukukçularına iletiniz. Kurumsal güvence ihtiyacı varsa not doğrudan meslek odaları veya platformlar üzerinden paylaşılabilir.</p>
    </div>
  </div>

  <h2>5. Bir Sayfalık Teknik İnceleme Notu Şablonu</h2>
  <pre>{_esc(template_text)}</pre>

  <h2>6. Çalışma İlkeleri ve Sürdürülebilirlik</h2>
  <ul>
    <li><strong>Kamuya açık ve yasal veri zemini:</strong> Platformda kullanılan tüm kayıtlar Bakanlığın kamuya açık duyuru sisteminden elde edilir. Madde 14 askı sürecinde görüş bildirmek, HKT toplantılarına katılmak ve İYUK 20/A kapsamında yargı yoluna başvurmak hukuk düzeninin tanıdığı yasal haklardır.</li>
    <li><strong>Bilimsel nesnellik ve doğrulanabilirlik:</strong> Yapay zeka ön taraması yalnızca hızlandırıcıdır; nihai dayanak daima resmi PDF belgesindeki <code>[s. N]</code> sayfalarıdır.</li>
    <li><strong>Tükenmişlikten uzak, esnek katkı:</strong> Hiçbir uzmanın düzenli kota üstlenmesi gerekmez. Ayda tek bir kritik dosyayı bir ya da iki saatte doğrulayıp yetkili hukuk ve meslek ağına ulaştırmak uzun vadede kalıcı kamusal fayda üretir.</li>
  </ul>

  <div class="notice">
    <strong>Yasal Bilgilendirme:</strong> Bu platform yalnızca kamuoyu şeffaflığı ve bilgilendirme amacıyla hazırlanmış olup hukuki danışmanlık niteliği taşımaz. Tüm yasal sürelerin, dava ehliyeti şartlarının ve güncel mevzuat değişikliklerinin herhangi bir başvuru öncesinde avukat tarafından doğrulanması gerekmektedir.
  </div>
</div>
</body>
</html>
"""


def _urgency_rank_value(filing: dict[str, Any]) -> int:
    """Numeric rank for urgency sorting (lower = more urgent).
    0..99    = Hard statutory deadline (İYUK 20/A 30d or Madde 14 10d askı), active
    200..399 = Scheduled upcoming HKT / İDK meeting date
    500      = Undated HKT / İDK notice
    800      = Open pre-decision review stage (ÇED Süreci Başlayan, m. 8/16)
    10000    = Expired deadline or closed/returned filing
    """
    clocks = filing.get("statutory_clocks") or []
    hard_days = [
        c["days_remaining"]
        for c in clocks
        if c.get("code") in ("iyuk_20a", "aski_10d")
        and c.get("days_remaining") is not None
        and c["days_remaining"] >= 0
    ]
    if hard_days:
        return min(hard_days)
    meeting_days = [
        c["days_remaining"]
        for c in clocks
        if c.get("code") in ("hkt", "idk")
        and c.get("days_remaining") is not None
        and c["days_remaining"] >= 0
    ]
    if meeting_days:
        return 200 + min(meeting_days)
    if any(c.get("code") in ("hkt", "idk") and c.get("days_remaining") is None for c in clocks):
        return 500
    if any(c.get("code") == "process_open" for c in clocks):
        return 800
    return 10000


def _urgency_sort_key(filing: dict[str, Any]) -> tuple[int, str]:
    ann = filing.get("announcement_date") or "0000-00-00"
    inv_date = "".join(chr(ord("9") - ord(ch) + ord("0")) if ch.isdigit() else ch for ch in ann)
    return (_urgency_rank_value(filing), inv_date)


def build_site(
    filings: list[dict[str, Any]],
    *,
    digests_dir: Path,
    docs_dir: Path,
    site_url: str = "https://yanekyuk.github.io/eced-watchdog/",
    max_cards: int = 300,
) -> dict[str, Any]:
    docs_dir.mkdir(parents=True, exist_ok=True)
    docs_digests = docs_dir / "digests"
    docs_digests.mkdir(parents=True, exist_ok=True)

    digests_index: set[str] = set()
    llm_summaries: dict[str, dict[str, Any]] = {}
    geo_by_fid: dict[str, dict[str, Any]] = {}

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
            if saved.get("analysis") and saved["analysis"].get("geo"):
                geo_by_fid[fid] = saved["analysis"]["geo"]

    # Keep the latest max_cards filings by date, then default-order by statutory urgency (least time remaining first)
    recent_pool = filings[:max_cards]
    shown_filings = sorted(recent_pool, key=_urgency_sort_key)
    total = len(shown_filings)
    provinces_present = sorted({f.get("province", "") for f in shown_filings if f.get("province")})
    active_count = sum(
        1
        for f in shown_filings
        if any(
            c.get("days_remaining") is None or c.get("days_remaining", -1) >= 0
            for c in f.get("statutory_clocks") or []
        )
    )
    ek1_count = sum(1 for f in shown_filings if f.get("project_type") == "Ek-1")
    digested_count = sum(
        1
        for f in shown_filings
        if (f.get("documents") or [{}])[0].get("filing_id") in digests_index
    )

    cards_html: list[str] = []
    map_items: list[dict[str, Any]] = []
    exact_geo_count = 0

    for idx, f in enumerate(shown_filings):
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
        is_ek1 = f.get("project_type") == "Ek-1"

        geo = geo_by_fid.get(fid)
        if geo and geo.get("precision") == "exact_pdf" and geo.get("lat") and geo.get("lon"):
            lat, lon = geo["lat"], geo["lon"]
            precision = "exact_pdf"
            exact_geo_count += 1
        else:
            lat, lon = province_centroid(f.get("province", ""), jitter_key=f.get("filing_key") or str(idx))
            precision = "province_centroid"

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
            actions.append(f'<a href="digests/{_esc(fid)}.md">Ham Markdown (.md)</a>')
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
                llm_badge = f'<span class="badge urgent">Teknik Ön İnceleme · {high_flags} yüksek / {total_flags} bulgu</span>'
            else:
                llm_badge = f'<span class="badge ok">Teknik Ön İnceleme · {total_flags} bulgu</span>'
            llm_preview = (
                f'<div class="detail" style="color:var(--text);">'
                f'<strong>Özet:</strong> {_esc(lres.get("executive_summary_tr", ""))}</div>'
            )

        map_items.append(
            {
                "idx": idx,
                "lat": lat,
                "lon": lon,
                "precision": precision,
                "color": _marker_color(f, has_digest),
                "province": f.get("province", ""),
                "district": f.get("district", ""),
                "title": (f.get("project_name") or "")[:120],
                "stage": f.get("decision_type", ""),
                "annex": f.get("project_type", ""),
                "date": f.get("announcement_date_tr", ""),
                "digest_url": f"digests/{fid}.html" if has_digest else None,
                "portal_url": portal_url or None,
            }
        )

        cards_html.append(
            f"""<article class="card {'ek1' if is_ek1 else ''}"
  data-idx="{idx}"
  data-urgency="{_urgency_rank_value(f)}"
  data-date="{_esc(f.get('announcement_date') or '0000-00-00')}"
  data-province="{_esc(f.get('province', ''))}"
  data-active="{'1' if is_active else '0'}"
  data-digest="{'1' if has_digest else '0'}"
  data-exactgeo="{'1' if precision == 'exact_pdf' else '0'}"
  data-annex="{_esc(f.get('project_type', ''))}"
  data-search="{_esc(search_blob)}">
  <div class="row-top">
    <div class="title">{_esc(f.get('project_name', ''))}</div>
    <div style="font-size:0.82rem;color:var(--muted);white-space:nowrap;">{_esc(f.get('announcement_date_tr', ''))}</div>
  </div>
  <div class="badges">
    <span class="badge">{_esc(f.get('province', ''))} · {_esc(f.get('district', ''))}</span>
    <span class="badge">{_esc(f.get('decision_type', ''))}</span>
    <span class="badge">{_esc(f.get('project_type', ''))}</span>
    <span class="badge muted">{_esc(f.get('sector', ''))}</span>
    {'<span class="badge ok">PDF Koordinatı</span>' if precision == 'exact_pdf' else ''}
    {_clock_badge_html(clock)}
    {llm_badge}
  </div>
  {llm_preview}
  <div class="detail"><strong>{_esc(f.get('project_owner', ''))}</strong> — {_esc(detail_short)}</div>
  <div class="actions">{' · '.join(actions)}</div>
</article>"""
        )

    prov_options = "\n".join(
        f'<option value="{_esc(p)}">{_esc(p)}</option>' for p in provinces_present
    )

    built_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    map_json = json.dumps(map_items, ensure_ascii=False)

    index_html = f"""<!doctype html>
<html lang="tr">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>Türkiye e-ÇED İzleme Platformu</title>
  <link rel="alternate" type="application/rss+xml" title="Türkiye e-ÇED İzleme RSS" href="feed.xml" />
  <link rel="stylesheet" href="{LEAFLET_CSS}" />
  <style>{BASE_CSS}</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>Türkiye e-ÇED İzleme Platformu</h1>
    <p class="sub">T.C. Çevre, Şehircilik ve İklim Değişikliği Bakanlığı'nın 81 ildeki kamuya açık ÇED duyuruları için yasal süre sayacı (10 günlük askı ve 30 günlük İYUK Madde 20/A), etkileşimli harita ve sayfa kaynaklı teknik ön özetler.</p>
    <div class="meta-bar">
      <span><strong><a href="rehber.html">Kullanım ve Bilimsel İnceleme Rehberi</a></strong></span>
      <span>Son güncelleme: <code>{_esc(built_at)}</code></span>
      <span><a href="feed.xml">RSS 2.0 Akışı (feed.xml)</a></span>
      <span>Resmi kaynak: <a href="https://eced-duyuru.csb.gov.tr/eced-prod/duyurular.xhtml" target="_blank" rel="noopener">eced-duyuru.csb.gov.tr</a></span>
    </div>
  </header>

  <section class="stats">
    <div class="stat"><div class="num">{total}</div><div class="lbl">Listelenen Duyuru ({len(provinces_present)} il)</div></div>
    <div class="stat"><div class="num">{active_count}</div><div class="lbl">Yasal Süresi Devam Eden</div></div>
    <div class="stat"><div class="num">{ek1_count}</div><div class="lbl">Ek-1 (ÇED Raporu)</div></div>
    <div class="stat"><div class="num">{digested_count}</div><div class="lbl">Ön Özeti Hazır Dosya</div></div>
  </section>

  <section class="map-box">
    <div id="map"></div>
    <div class="map-legend">
      <span><span class="dot" style="background:#f85149"></span>Acil yasal süre (≤ 7 gün)</span>
      <span><span class="dot" style="background:#d29922"></span>Yaklaşan süre / HKT / İDK</span>
      <span><span class="dot" style="background:#3fb950"></span>Devam eden İYUK 20/A süresi (&gt; 15 gün)</span>
      <span><span class="dot" style="background:#58a6ff"></span>Karar öncesi inceleme (m. 8/16)</span>
      <span><span class="dot" style="background:#6e7681"></span>Süresi dolmuş / iade</span>
      <span><strong>Beyaz çerçeveli nokta:</strong> PDF'ten çıkarılmış kesin koordinat · <strong>Yarı saydam nokta:</strong> Yaklaşık il merkezi</span>
    </div>
  </section>

  <section class="controls">
    <input id="q" type="search" placeholder="İl, ilçe, proje adı, şirket, sektör veya dosya numarası arayınız…" />
    <select id="prov" class="filter-select" aria-label="İl filtresi">
      <option value="">Tüm İller ({len(provinces_present)})</option>
      {prov_options}
    </select>
    <select id="sort" class="filter-select" aria-label="Sıralama ölçütü">
      <option value="urgent" selected>Sıralama: En acil yasal süre</option>
      <option value="newest">Sıralama: En yeni duyuru</option>
      <option value="digest">Sıralama: Ön özeti hazır olanlar</option>
      <option value="ek1">Sıralama: Ek-1 öncelikli</option>
    </select>
    <button class="pill active" data-filter="all">Tümü</button>
    <button class="pill" data-filter="active">Yasal Süresi Devam Edenler</button>
    <button class="pill" data-filter="digest">Ön Özeti Hazır Olanlar</button>
    <button class="pill" data-filter="ek1">Yalnızca Ek-1</button>
  </section>

  <div id="count" class="sub" style="margin-bottom:10px;">Toplam {total} duyuru gösterilmektedir.</div>
  <main class="cards" id="cards">
    {''.join(cards_html)}
  </main>

  <div class="notice">
    <strong>Yasal Bilgilendirme:</strong> Bu platformda yer alan tüm kayıtlar T.C. Çevre, Şehircilik ve İklim Değişikliği Bakanlığı'nın kamuya açık e-ÇED duyuru portalından alınmaktadır. 2577 sayılı İdari Yargılama Usulü Kanunu'nun (İYUK) 20/A maddesi uyarınca ÇED kararlarına karşı iptal davası açma süresi <strong>30 gündür</strong> ve <em>İYUK Madde 11 kapsamında idareye yapılan başvurular bu süreyi durdurmaz</em>. Kesin tarih ve hukuki süreçler için yetkili hukukçulardan görüş alınması gerekmektedir.
  </div>
</div>
<script src="{LEAFLET_JS}"></script>
<script>
(() => {{
  const cardsContainer = document.getElementById('cards');
  const cards = [...document.querySelectorAll('#cards article')];
  const pills = [...document.querySelectorAll('button.pill')];
  const q = document.getElementById('q');
  const prov = document.getElementById('prov');
  const sortSel = document.getElementById('sort');
  const countEl = document.getElementById('count');
  const mapItems = {map_json};
  let mode = 'all';

  function sortCards() {{
    const s = sortSel.value;
    cards.sort((a, b) => {{
      const ua = Number(a.dataset.urgency);
      const ub = Number(b.dataset.urgency);
      const da = a.dataset.date;
      const db = b.dataset.date;
      if (s === 'newest') {{
        if (db !== da) return db.localeCompare(da);
        return ua - ub;
      }}
      if (s === 'digest') {{
        const ha = Number(b.dataset.digest) - Number(a.dataset.digest);
        if (ha !== 0) return ha;
        if (ua !== ub) return ua - ub;
        return db.localeCompare(da);
      }}
      if (s === 'ek1') {{
        const ea = (b.dataset.annex === 'Ek-1' ? 1 : 0) - (a.dataset.annex === 'Ek-1' ? 1 : 0);
        if (ea !== 0) return ea;
        if (ua !== ub) return ua - ub;
        return db.localeCompare(da);
      }}
      // Default: urgent (least time remaining first)
      if (ua !== ub) return ua - ub;
      return db.localeCompare(da);
    }});
    for (const c of cards) cardsContainer.appendChild(c);
  }}

  let map = null;
  let layerGroup = null;
  if (typeof L !== 'undefined') {{
    map = L.map('map').setView([39.0, 35.2], 6);
    L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
      maxZoom: 18,
      attribution: '&copy; OpenStreetMap katkıda bulunanları'
    }}).addTo(map);
    layerGroup = L.layerGroup().addTo(map);
  }}

  function escHtml(s) {{
    return String(s || '').replace(/[&<>"']/g, m => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[m]));
  }}

  function renderMap(visibleIdxSet) {{
    if (!layerGroup) return;
    layerGroup.clearLayers();
    const bounds = [];
    for (const item of mapItems) {{
      if (!visibleIdxSet.has(item.idx)) continue;
      const isExact = item.precision === 'exact_pdf';
      const marker = L.circleMarker([item.lat, item.lon], {{
        radius: isExact ? 7 : 6,
        color: isExact ? '#ffffff' : item.color,
        weight: isExact ? 2 : 1,
        fillColor: item.color,
        fillOpacity: isExact ? 0.92 : 0.55
      }});
      const links = [];
      if (item.digest_url) links.push(`<a href="${{item.digest_url}}"><strong>Sayfa Kaynaklı Ön Özet</strong></a>`);
      if (item.portal_url) links.push(`<a href="${{item.portal_url}}" target="_blank" rel="noopener">Resmi e-ÇED Kaydı</a>`);
      const locNote = isExact ? 'PDF metninden çıkarılan kesin koordinat' : 'Yaklaşık il merkezi konumu';
      marker.bindPopup(
        `<strong>${{escHtml(item.province)}} / ${{escHtml(item.district)}}</strong><br/>` +
        `${{escHtml(item.title)}}<br/>` +
        `<span style="color:#57606a">${{escHtml(item.stage)}} · ${{escHtml(item.annex)}} · ${{escHtml(item.date)}}</span><br/>` +
        `<small style="color:#57606a">${{locNote}}</small><br/>` +
        links.join(' · ')
      );
      marker.addTo(layerGroup);
      bounds.push([item.lat, item.lon]);
    }}
    if (prov.value && bounds.length > 0) {{
      map.fitBounds(bounds, {{ maxZoom: 10, padding: [30, 30] }});
    }} else if (!prov.value && !q.value.trim()) {{
      map.setView([39.0, 35.2], 6);
    }}
  }}

  function apply() {{
    const term = q.value.trim().toLowerCase();
    const selectedProv = prov.value;
    const visibleSet = new Set();
    for (const c of cards) {{
      let ok = true;
      if (mode === 'active') ok = c.dataset.active === '1';
      else if (mode === 'digest') ok = c.dataset.digest === '1';
      else if (mode === 'ek1') ok = c.dataset.annex === 'Ek-1';
      if (ok && selectedProv) ok = c.dataset.province === selectedProv;
      if (ok && term) ok = c.dataset.search.includes(term);
      c.style.display = ok ? '' : 'none';
      if (ok) visibleSet.add(Number(c.dataset.idx));
    }}
    countEl.textContent = `Toplam ${{cards.length}} duyurudan ${{visibleSet.size}} tanesi gösterilmektedir.`;
    renderMap(visibleSet);
  }}

  pills.forEach(p => p.addEventListener('click', () => {{
    pills.forEach(x => x.classList.remove('active'));
    p.classList.add('active');
    mode = p.dataset.filter;
    apply();
  }}));
  q.addEventListener('input', apply);
  prov.addEventListener('change', apply);
  sortSel.addEventListener('change', () => {{
    sortCards();
    apply();
  }});
  sortCards();
  apply();
}})();
</script>
</body>
</html>
"""
    (docs_dir / "index.html").write_text(index_html, encoding="utf-8")
    (docs_dir / "rehber.html").write_text(render_guide_html(), encoding="utf-8")
    rss_xml = build_rss(shown_filings, digests_index, site_url)
    (docs_dir / "feed.xml").write_text(rss_xml, encoding="utf-8")

    return {
        "total": total,
        "provinces": len(provinces_present),
        "active": active_count,
        "digests_rendered": len(digests_index),
        "exact_geo": exact_geo_count,
        "index_path": str(docs_dir / "index.html"),
        "feed_path": str(docs_dir / "feed.xml"),
    }

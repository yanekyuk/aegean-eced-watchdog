"""Deterministic, page-cited PyMuPDF extractor & 1-page Markdown pre-digest generator."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import httpx
import pymupdf as fitz

from .fetcher import USER_AGENT, build_ssl_context
from .geo import extract_pdf_coordinates
from .llm import synthesize_with_gemini

SIGNAL_SPECS: list[tuple[str, str, str]] = [
    (
        "coordinates_and_footprint",
        "Coordinates, Parcel & Footprint",
        r"(?:(\d+[.,]\d+\s*(?:hektar|ha\b|m2|m²|km2|km²|km\b))|"
        r"(?:ada\s*[:/]?\s*\d+[^.\n]{0,40}parsel)|"
        r"(?:ED[\s-]?50|WGS[\s-]?84|UTM|ITRF|koordinat))",
    ),
    (
        "water_and_discharge",
        "Water Use, Hydrogeology & Discharge",
        r"(?:(\d+[.,]?\d*\s*(?:m3/gün|m³/gün|m3/yıl|m³/yıl|lt/sn|l/s|m3/saat|m³/saat|ton/gün))|"
        r"\b(?:reenjeksiyon|akifer|yeraltı\s*suyu|deşarj|atıksu|dere\s*yatağı|sulak\s*alan|"
        r"deniz\s*suyu|ötrofikasyon|kuyu\s*derinliği)\b)",
    ),
    (
        "protected_land_and_olive",
        "Protected Zones, Forests & Olive Groves",
        r"\b(?:zeytinlik|3573\s*sayılı|orman\s*alanı|özel\s*çevre\s*koruma|ÖÇK|"
        r"sit\s*alanı|arkeolojik\s*sit|doğal\s*sit|mutlak\s*tarım|mera\s*alanı|"
        r"milli\s*park|tabiat\s*parkı|sulak\s*alan|kıyı\s*kenar)\b",
    ),
    (
        "ecology_and_baseline",
        "Flora, Fauna & Baseline Methodology",
        r"\b(?:endemik|IUCN|Bern\s*Sözleşmesi|CITES|kırmızı\s*liste|kuş\s*göç|göç\s*yolu|"
        r"arazi\s*çalışması|literatür\s*taraması|mevsimsel|örnekleme|biyoçeşitlilik|"
        r"habitat\s*parçalanması|flora\s*ve\s*fauna)\b",
    ),
    (
        "pollutants_and_hazards",
        "Emissions, Geochemistry & Waste",
        r"\b(?:H2S|hidrojen\s*sülfür|bor\b|arsenik|ağır\s*metal|karbondioksit|CO2|"
        r"tehlikeli\s*atık|sondaj\s*çamuru|toz\s*emisyon|PM10|PM2[.,]5|"
        r"elektromanyetik|gürültü|fay\s*hattı|deprem|kümülatif)\b",
    ),
    (
        "cost_and_capacity",
        "Project Cost, Power & Capacity",
        r"(?:(\d{1,3}(?:[.,]\d{3})+\s*(?:TL|USD|Euro|€|\$|kW|MW|kV|ton/yıl|ton/gün))|"
        r"(?:proje\s*bedeli|kurulu\s*güç|kapasite))",
    ),
]


def download_pdf(pdf_url: str, dest: Path, cert_path: Path | None) -> dict[str, Any]:
    if dest.exists() and dest.stat().st_size > 1000:
        data = dest.read_bytes()
        return {
            "filename": dest.name,
            "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
            "cached": True,
        }

    ctx = build_ssl_context(cert_path)
    with httpx.Client(
        verify=ctx,
        http2=False,
        headers={"User-Agent": USER_AGENT},
        timeout=90.0,
        follow_redirects=True,
    ) as client:
        resp = client.get(pdf_url)
        resp.raise_for_status()
        data = resp.content
        if not data[:5].startswith(b"%PDF"):
            raise RuntimeError(
                f"Expected PDF from {pdf_url}, got content-type={resp.headers.get('content-type')}"
            )
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        return {
            "filename": dest.name,
            "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
            "cached": False,
        }


def _clean_snippet(text: str, start: int, end: int, radius: int = 120) -> str:
    lo = max(0, start - radius)
    hi = min(len(text), end + radius)
    frag = re.sub(r"\s+", " ", text[lo:hi]).strip()
    if lo > 0:
        frag = "…" + frag
    if hi < len(text):
        frag = frag + "…"
    return frag


def _is_toc_or_header_noise(page_text: str, start: int, end: int) -> bool:
    if start < 160 and page_text[:160].count("\n") <= 4:
        return True
    line_start = page_text.rfind("\n", 0, start) + 1
    line_end = page_text.find("\n", end)
    if line_end == -1:
        line_end = len(page_text)
    line = page_text[line_start:line_end]
    return "...." in line or ". . ." in line or bool(re.search(r"\.{3,}\s*\d+", line))


def _extract_headings(doc: fitz.Document, page_texts: list[str]) -> list[tuple[int, str]]:
    toc = [(p, title.strip()) for _lvl, title, p in doc.get_toc() if p > 0 and title.strip()]
    if len(toc) >= 5 and not any(t.lower().endswith(".pdf") for _, t in toc[:5]):
        return toc[:25]

    headings: list[tuple[int, str]] = []
    seen: set[str] = set()
    heading_re = re.compile(
        r"^(?:BÖLÜM\s+[IVX0-9]+[^\n]{0,95}|"
        r"PROJENİN\s+TEKNİK\s+OLMAYAN\s+ÖZETİ[^\n]{0,40}|"
        r"FLORA\s+[Vv][Ee]\s+FAUNA[^\n]{0,40}|"
        r"KÜMÜLATİF\s+ETKİ[^\n]{0,60}|"
        r"ÇEVRESEL\s+VE\s+SOSYAL[^\n]{0,60})$",
        re.M,
    )
    for idx, txt in enumerate(page_texts, start=1):
        for m in heading_re.finditer(txt):
            h = re.sub(r"\s+", " ", m.group(0)).strip()
            if "...." in h or ". . ." in h or re.search(r"\s\d{1,3}$", h):
                continue
            key = h.lower()
            if key not in seen and len(h) < 110:
                seen.add(key)
                headings.append((idx, h))
        if len(headings) >= 22:
            break
    return headings


def analyze_pdf(pdf_path: Path, province: str = "") -> dict[str, Any]:
    doc = fitz.open(pdf_path)
    page_texts: list[str] = []
    scanned_pages: list[int] = []
    total_chars = 0

    for i, page in enumerate(doc, start=1):
        txt = page.get_text("text") or ""
        page_texts.append(txt)
        n = len(txt.strip())
        total_chars += n
        if n < 40:
            scanned_pages.append(i)

    headings = _extract_headings(doc, page_texts)
    geo = extract_pdf_coordinates(page_texts, province)

    signals: dict[str, dict[str, Any]] = {}
    for key, label, pattern in SIGNAL_SPECS:
        rx = re.compile(pattern, re.I)
        hits: list[dict[str, Any]] = []
        pages_hit: list[int] = []
        seen_keys: set[str] = set()
        for pno, txt in enumerate(page_texts, start=1):
            for m in rx.finditer(txt):
                if _is_toc_or_header_noise(txt, m.start(), m.end()):
                    continue
                if pno not in pages_hit:
                    pages_hit.append(pno)
                if len(hits) < 8:
                    match_clean = re.sub(r"\s+", " ", m.group(0)).strip()
                    snip = _clean_snippet(txt, m.start(), m.end())
                    sig_key = f"{pno}:{match_clean.lower()}"
                    if sig_key not in seen_keys:
                        seen_keys.add(sig_key)
                        hits.append({"page": pno, "match": match_clean, "snippet": snip})
        signals[key] = {
            "label": label,
            "page_count": len(pages_hit),
            "pages": pages_hit[:25],
            "samples": hits,
        }

    full_text_lower = "\n".join(page_texts).lower()
    checks = {
        "mentions_field_survey": bool(re.search(r"arazi\s*çalışma|saha\s*çalışma|yerinde\s*inceleme", full_text_lower)),
        "mentions_literature_only_cue": bool(re.search(r"literatür\s*tarama|literatür\s*verileri", full_text_lower)),
        "mentions_seasonal_sampling": bool(re.search(r"mevsimsel|dört\s*mevsim|ilkbahar.{0,40}sonbahar", full_text_lower)),
        "mentions_cumulative_impact": bool(re.search(r"kümülatif|birikimli\s*etki", full_text_lower)),
        "mentions_olive_law_3573": bool(re.search(r"3573|zeytinlik", full_text_lower)),
        "mentions_groundwater_or_aquifer": bool(re.search(r"yeraltı\s*su|akifer|hidrojeoloj", full_text_lower)),
        "mentions_iucn_or_endemic": bool(re.search(r"iucn|endemik|bern\s*sözleşme", full_text_lower)),
    }

    page_count = len(doc)
    doc.close()
    return {
        "page_count": page_count,
        "total_chars": total_chars,
        "text_pages": page_count - len(scanned_pages),
        "scanned_or_blank_pages": len(scanned_pages),
        "scanned_page_sample": scanned_pages[:15],
        "headings": headings,
        "geo": geo,
        "signals": signals,
        "audit_checks": checks,
    }


def render_markdown_digest(
    filing: dict[str, Any],
    doc_meta: dict[str, Any],
    pdf_info: dict[str, Any],
    analysis: dict[str, Any],
    llm_synthesis: dict[str, Any] | None = None,
) -> str:
    filing_id = doc_meta.get("filing_id") or "unknown"
    pdf_url = doc_meta["pdf_urls"][0]["url"] if doc_meta.get("pdf_urls") else ""
    clocks = filing.get("statutory_clocks", [])
    clock_lines = (
        "\n".join(
            f"- **{c['kind']}:** `{c['deadline'] or 'see text'}` "
            + (f"(`{c['days_remaining']} days remaining`)" if c.get("days_remaining") is not None else "")
            for c in clocks
        )
        or "- *(No automatic clock computed; verify decision type in official text)*"
    )

    checks = analysis["audit_checks"]
    flag = lambda ok: "Present" if ok else "**NOT FOUND (check manually)**"

    lines = [
        f"# e-ÇED Pre-Digest — #{filing_id} ({filing['district']} / {filing['province']})",
        "",
        f"> **Official Portal:** {doc_meta.get('portal_doc_url', '')}",
        f"> **Direct PDF:** {pdf_url}",
        f"> **PDF SHA-256:** `{pdf_info['sha256'][:16]}…` ({pdf_info['bytes'] / 1024 / 1024:.2f} MB · {analysis['page_count']} pages · {analysis['text_pages']} text / {analysis['scanned_or_blank_pages']} scanned-or-image)",
        "",
        "## 1. Filing Metadata & Statutory Clocks",
        "",
        "| Field | Value |",
        "|---|---|",
        f"| **Project** | {filing['project_name']} |",
        f"| **Owner** | {filing['project_owner']} |",
        f"| **Consulting Firm** | {doc_meta.get('consulting_firm') or '—'} |",
        f"| **District / Sector** | {filing['district']} · {filing['sector']} / {filing['sub_sector']} |",
        f"| **Stage / Annex** | `{filing['decision_type']}` · `{filing['project_type']}` |",
        f"| **Announcement Date** | `{filing['announcement_date_tr']}` (uploaded `{doc_meta.get('submitted_at') or '—'}`) |",
        "",
        "**Statutory Deadlines (informational aid — verify with legal counsel):**",
        clock_lines,
        "",
    ]

    if llm_synthesis and llm_synthesis.get("result"):
        res = llm_synthesis["result"]
        ba = res["baseline_assessment"]
        pages_used = ", ".join(f"s.{p}" for p in llm_synthesis.get("pages_sent") or [])
        lines.extend(
            [
                f"## 2. AI-Assisted Scientific Synthesis (`{llm_synthesis.get('model')}`)",
                "",
                f"> *Generated from {len(llm_synthesis.get('pages_sent') or [])} excerpted PDF pages ({pages_used}). Verify every figure against `[s. N]` in the official PDF.*",
                "",
                f"**Özet (TR):** {res['executive_summary_tr']}",
                "",
                f"**Summary (EN):** {res['executive_summary_en']}",
                "",
                "### Key Extracted Figures",
                "",
            ]
        )
        for kf in res.get("key_facts") or []:
            lines.append(f"- **{kf['label']}:** {kf['value']} (`[s. {kf['page']}]`)")
        lines.extend(
            [
                "",
                "### Baseline & Methodology Assessment",
                "",
                f"- **Field survey:** `{ba['field_survey_status']}`",
                f"- **Seasonal sampling:** `{ba['seasonal_sampling_status']}`",
                f"- **Cumulative impact:** `{ba['cumulative_impact_status']}`",
                f"- **Olive Law / protected areas:** {ba['olive_and_protected_status']}",
                f"- **Assessment:** {ba['explanation']}",
                "",
                "### Scientific Audit Red Flags",
                "",
            ]
        )
        for rf in res.get("red_flags") or []:
            p_tags = ", ".join(f"s.{p}" for p in rf.get("pages") or [])
            lines.append(f"- **[{rf['severity'].upper()}] {rf['title']}** (`{p_tags}`): {rf['detail']}")
        lines.extend(
            [
                "",
                "### Draft Technical Questions (HKT / İYUK 20/A)",
                "",
            ]
        )
        for q in res.get("hkt_and_petition_questions") or []:
            p_tags = ", ".join(f"s.{p}" for p in q.get("pages") or [])
            lines.append(f"- {q['question_tr']} (`{p_tags}`)")
        lines.extend(
            [
                "",
                f"*Limitations:* {res.get('data_limitations', '')}",
                "",
            ]
        )

    lines.extend(
        [
            "## Official Announcement Text",
            "",
            f"> {filing.get('detail_text', '')}",
            "",
            "## Deterministic Baseline & Red-Flag Scan",
            "",
            "| Check | Status in Extractable Text |",
            "|---|---|",
            f"| Field survey mentioned (*arazi/saha çalışması*) | {flag(checks['mentions_field_survey'])} |",
            f"| Literature-review cue (*literatür taraması*) | {flag(checks['mentions_literature_only_cue'])} |",
            f"| Seasonal sampling mentioned (*mevsimsel*) | {flag(checks['mentions_seasonal_sampling'])} |",
            f"| Cumulative impact assessed (*kümülatif*) | {flag(checks['mentions_cumulative_impact'])} |",
            f"| Olive Law / groves (*3573 / zeytinlik*) | {flag(checks['mentions_olive_law_3573'])} |",
            f"| Groundwater / hydrogeology (*akifer / yeraltı suyu*) | {flag(checks['mentions_groundwater_or_aquifer'])} |",
            f"| Endemic / IUCN / Bern Convention | {flag(checks['mentions_iucn_or_endemic'])} |",
            "",
            "*(Scanned annex maps/appendices without OCR are excluded from text scan; see scanned-page count above.)*",
            "",
            "## Page-Cited Extracted Evidence",
            "",
        ]
    )

    for _key, sig in analysis["signals"].items():
        pages_preview = ", ".join(f"s.{p}" for p in sig["pages"][:12])
        if sig["page_count"] > 12:
            pages_preview += f" (+{sig['page_count'] - 12} more)"
        lines.append(f"### {sig['label']} ({sig['page_count']} pages: {pages_preview or 'none'})")
        if not sig["samples"]:
            lines.append("- *No text matches found.*")
        else:
            for h in sig["samples"][:5]:
                lines.append(f"- **[s. {h['page']}]** `{h['match']}` — {h['snippet']}")
        lines.append("")

    if analysis["headings"]:
        lines.append("## Document Navigation Map (Detected Headings)")
        lines.append("")
        for pno, h in analysis["headings"][:18]:
            lines.append(f"- **[s. {pno}]** {h}")
        lines.append("")

    lines.extend(
        [
            "## Scientist Audit Notes (1–2h Async Review Template)",
            "",
            "- **Baseline & sampling gaps (`[s. N]`):** ",
            "- **Ecological / hydrological contradictions:** ",
            "- **Cumulative regional impact omitted:** ",
            "- **Questions for HKT minutes / İYUK 20/A petition:** ",
            "- **Recommended hand-off:** İzmir Barosu Çevre Komisyonu / TMMOB / EGEÇEP / Local press",
            "",
        ]
    )
    return "\n".join(lines)


def ensure_digest_for_filing(
    filing: dict[str, Any],
    *,
    digests_dir: Path,
    pdfs_dir: Path,
    cert_path: Path | None,
    keep_pdf: bool = True,
    gemini_api_key: str | None = None,
    gemini_model: str | None = None,
    re_synthesize: bool = False,
) -> dict[str, Any] | None:
    docs = filing.get("documents") or []
    if not docs or not docs[0].get("pdf_urls"):
        return None
    doc_meta = docs[0]
    filing_id = doc_meta.get("filing_id")
    if not filing_id:
        return None

    md_path = digests_dir / f"{filing_id}_digest.md"
    json_path = digests_dir / f"{filing_id}_analysis.json"
    pdf_url = doc_meta["pdf_urls"][0]["url"]
    pdf_path = pdfs_dir / f"{filing_id}.pdf"

    llm_synthesis: dict[str, Any] | None = None
    synthesized_now = False

    if json_path.exists() and md_path.exists():
        saved = json.loads(json_path.read_text(encoding="utf-8"))
        pdf_info = saved["pdf_info"]
        analysis = saved["analysis"]
        llm_synthesis = saved.get("llm_synthesis")
        cached = True
    else:
        pdf_info = download_pdf(pdf_url, pdf_path, cert_path)
        analysis = analyze_pdf(pdf_path, province=filing.get("province", ""))
        cached = False

    need_llm = bool(gemini_api_key) and (re_synthesize or not llm_synthesis)
    if need_llm:
        if not pdf_path.exists():
            pdf_info = download_pdf(pdf_url, pdf_path, cert_path)
        llm_synthesis = synthesize_with_gemini(
            filing,
            analysis,
            pdf_path,
            api_key=gemini_api_key,
            model=gemini_model,
        )
        synthesized_now = True

    if not keep_pdf and pdf_path.exists():
        pdf_path.unlink(missing_ok=True)

    digests_dir.mkdir(parents=True, exist_ok=True)
    md = render_markdown_digest(filing, doc_meta, pdf_info, analysis, llm_synthesis=llm_synthesis)
    md_path.write_text(md, encoding="utf-8")
    payload: dict[str, Any] = {
        "filing": filing,
        "pdf_info": pdf_info,
        "analysis": analysis,
    }
    if llm_synthesis:
        payload["llm_synthesis"] = llm_synthesis
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "filing_id": filing_id,
        "md_path": str(md_path),
        "json_path": str(json_path),
        "cached": cached,
        "synthesized_now": synthesized_now,
        "analysis": analysis,
        "pdf_info": pdf_info,
        "llm_synthesis": llm_synthesis,
    }

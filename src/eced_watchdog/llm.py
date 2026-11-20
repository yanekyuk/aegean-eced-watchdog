"""Optional Gemini API structured-output synthesis layer over deterministic PDF page extracts."""

from __future__ import annotations

import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

import pymupdf as fitz
from pydantic import BaseModel, Field

DEFAULT_EK1_MODEL = "gemini-4-hydrogen"
DEFAULT_EK2_MODEL = "gemini-3.5-flash-lite"
DEFAULT_GEMINI_MODEL = DEFAULT_EK1_MODEL


def choose_gemini_model(filing: dict[str, Any], explicit_model: str | None = None) -> str:
    """Use explicit/env model if set; otherwise route Ek-1 to Gemini 4 Hydrogen and Ek-2 to 3.5 Flash-Lite."""
    if explicit_model:
        return explicit_model
    env_model = os.environ.get("GEMINI_MODEL")
    if env_model:
        return env_model
    if (filing.get("project_type") or "").strip().lower() == "ek-1":
        return DEFAULT_EK1_MODEL
    return DEFAULT_EK2_MODEL


class CitedFact(BaseModel):
    label: str = Field(description="Short parameter label, e.g. 'Footprint / Length', 'Water Use', 'Nearest Settlement'.")
    value: str = Field(description="Exact stated number/claim from the report, with units.")
    page: int = Field(description="Exact 1-based PDF page number from the supplied excerpts.")


class BaselineAssessment(BaseModel):
    field_survey_status: Literal[
        "field_survey_documented",
        "literature_only",
        "mixed_or_unclear",
        "not_found",
    ] = Field(description="Whether actual field surveys were conducted vs. literature-only species/habitat lists.")
    seasonal_sampling_status: Literal[
        "completed_pre_project",
        "promised_post_approval_only",
        "not_found",
        "unclear",
    ] = Field(
        description=(
            "Distinguish strictly between multi-season baseline sampling ALREADY completed before filing "
            "vs. seasonal monitoring merely PROMISED after approval."
        )
    )
    cumulative_impact_status: Literal[
        "quantitatively_assessed",
        "superficial_or_boilerplate",
        "omitted_or_not_found",
    ] = Field(description="Quality of cumulative regional impact evaluation.")
    olive_and_protected_status: str = Field(
        description="Concise factual summary of olive groves (Law 3573), forests, wetlands, ÖÇK/SİT status with [s. N]."
    )
    explanation: str = Field(
        description="2-4 concise, neutral scientific sentences explaining the baseline findings with [s. N] page citations."
    )


class AuditRedFlag(BaseModel):
    severity: Literal["high", "medium", "low"]
    title: str = Field(description="Short concrete title of the methodological, ecological, or regulatory gap.")
    detail: str = Field(description="Factual explanation grounded strictly in the provided pages.")
    pages: list[int] = Field(description="1-based PDF page numbers supporting this finding.")


class RecordQuestion(BaseModel):
    question_tr: str = Field(
        description="Concise, neutral, technically sharp Turkish question for HKT minutes or administrative petition."
    )
    pages: list[int] = Field(description="Relevant 1-based PDF page numbers.")


class EcologicalSynthesis(BaseModel):
    executive_summary_tr: str = Field(
        description="3-5 sentence neutral Turkish summary: what is proposed, exact location/scale, and primary environmental stakes."
    )
    executive_summary_en: str = Field(
        description="3-5 sentence neutral English summary: what is proposed, exact location/scale, and primary environmental stakes."
    )
    key_facts: list[CitedFact] = Field(
        description="Up to 10 concrete quantitative facts extracted directly from the report with page citations."
    )
    baseline_assessment: BaselineAssessment
    red_flags: list[AuditRedFlag] = Field(
        description="Up to 6 concrete scientific/methodological gaps or omissions strictly supported by the excerpts."
    )
    hkt_and_petition_questions: list[RecordQuestion] = Field(
        description="3-5 concrete, neutral technical questions in Turkish for HKT minutes or İYUK 20/A review."
    )
    data_limitations: str = Field(
        description="Brief note on what could not be verified (e.g., scanned annex pages or sections outside excerpts)."
    )


def load_env_file(env_path: Path) -> None:
    """Load KEY=VALUE pairs from a local .env file without overriding existing env vars."""
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


def resolve_api_key(root: Path | None = None) -> str | None:
    if root:
        load_env_file(root / ".env")
    return os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")


def select_high_signal_pages(
    pdf_path: Path,
    analysis: dict[str, Any],
    *,
    max_pages: int = 26,
    max_chars: int = 75_000,
) -> tuple[list[int], str]:
    """Select the highest-signal body pages from the PDF for focused, page-cited synthesis."""
    doc = fitz.open(pdf_path)
    n_pages = len(doc)
    chosen: list[int] = []

    def add_page(pno: int) -> None:
        if 1 <= pno <= n_pages and pno not in chosen and len(chosen) < max_pages:
            chosen.append(pno)

    # 1. Cover / project card (pages 1-2)
    for p in (1, 2):
        add_page(p)

    # 2. Key detected section starts + immediate following page
    priority_heading_terms = (
        "teknik olmayan",
        "bölüm ii",
        "flora",
        "kümülatif",
        "çevresel ve sosyal",
        "bölüm i:",
    )
    for pno, title in analysis.get("headings") or []:
        t_low = title.lower()
        if any(term in t_low for term in priority_heading_terms):
            add_page(pno)
            add_page(pno + 1)

    # 3. Top pages from each deterministic signal bucket
    for bucket in (
        "protected_land_and_olive",
        "water_and_discharge",
        "ecology_and_baseline",
        "pollutants_and_hazards",
        "coordinates_and_footprint",
        "cost_and_capacity",
    ):
        sig = (analysis.get("signals") or {}).get(bucket) or {}
        for pno in (sig.get("pages") or [])[:4]:
            add_page(pno)

    # 4. Backfill early body pages (e.g. non-technical summary pages 6..15)
    for p in range(6, min(16, n_pages + 1)):
        add_page(p)

    chosen.sort()

    parts: list[str] = []
    used_pages: list[int] = []
    total_chars = 0
    for pno in chosen:
        txt = (doc[pno - 1].get_text("text") or "").strip()
        if len(txt) < 40:
            continue
        if len(txt) > 4500:
            txt = txt[:4500] + "\n[...page truncated...]"
        chunk = f"=== PDF PAGE [s. {pno}] ===\n{txt}\n"
        if total_chars + len(chunk) > max_chars and used_pages:
            break
        parts.append(chunk)
        used_pages.append(pno)
        total_chars += len(chunk)

    doc.close()
    return used_pages, "\n".join(parts)


def synthesize_with_gemini(
    filing: dict[str, Any],
    analysis: dict[str, Any],
    pdf_path: Path,
    *,
    api_key: str,
    model: str | None = None,
) -> dict[str, Any]:
    """Run strict schema-constrained Gemini Flash synthesis over selected PDF pages."""
    from google import genai
    from google.genai import types

    chosen_model = choose_gemini_model(filing, model)
    used_pages, excerpt_blob = select_high_signal_pages(pdf_path, analysis)

    system_instruction = (
        "You are an independent environmental scientist auditing an official Turkish Environmental Impact "
        "Assessment (ÇED / PTD) filing for public-interest transparency. "
        "Strict epistemic rules:\n"
        "1. Rely ONLY on the provided PDF page excerpts and filing metadata. Never invent figures, species, or claims.\n"
        "2. Every fact, red flag, and question MUST cite exact 1-based PDF page numbers from the === PDF PAGE [s. N] === markers.\n"
        "3. Explicitly distinguish completed pre-project baseline field/seasonal surveys from future post-approval monitoring promises.\n"
        "4. Stay strictly factual, neutral, and scientific — zero partisan commentary or legal accusations.\n"
        "5. Write key_facts labels/values, baseline explanation, olive_and_protected_status, red_flags, hkt_and_petition_questions, and data_limitations in clear, formal Turkish (only executive_summary_en should be in English)."
    )

    user_prompt = (
        f"FILING METADATA:\n"
        f"- Province / District: {filing.get('province')} / {filing.get('district')}\n"
        f"- Project: {filing.get('project_name')}\n"
        f"- Owner: {filing.get('project_owner')}\n"
        f"- Sector: {filing.get('sector')} / {filing.get('sub_sector')}\n"
        f"- Stage / Annex: {filing.get('decision_type')} / {filing.get('project_type')}\n"
        f"- Announcement Date: {filing.get('announcement_date_tr')}\n"
        f"- Total PDF Pages: {analysis.get('page_count')} "
        f"(extractable text: {analysis.get('text_pages')}, scanned/image-only: {analysis.get('scanned_or_blank_pages')})\n"
        f"- Pages Included Below: {used_pages}\n\n"
        f"OFFICIAL ANNOUNCEMENT:\n{filing.get('detail_text', '')}\n\n"
        f"EXCERPTED PDF PAGES:\n{excerpt_blob}"
    )

    client = genai.Client(api_key=api_key)
    config = types.GenerateContentConfig(
        system_instruction=system_instruction,
        temperature=0.1,
        response_mime_type="application/json",
        response_schema=EcologicalSynthesis,
    )

    last_err: Exception | None = None
    response = None
    for attempt, backoff in enumerate((4, 10, 20), start=1):
        try:
            response = client.models.generate_content(
                model=chosen_model,
                contents=user_prompt,
                config=config,
            )
            break
        except Exception as exc:
            last_err = exc
            msg = str(exc)
            if any(code in msg for code in ("503", "429", "UNAVAILABLE", "RESOURCE_EXHAUSTED")) and attempt < 3:
                time.sleep(backoff)
                continue
            raise
    if response is None:
        raise last_err or RuntimeError("Gemini synthesis returned no response")

    parsed = EcologicalSynthesis.model_validate_json(response.text)
    usage = getattr(response, "usage_metadata", None)
    usage_dict = None
    if usage is not None:
        usage_dict = {
            "prompt_tokens": getattr(usage, "prompt_token_count", None),
            "output_tokens": getattr(usage, "candidates_token_count", None),
            "thoughts_tokens": getattr(usage, "thoughts_token_count", None),
            "total_tokens": getattr(usage, "total_token_count", None),
        }
    return {
        "model": chosen_model,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "pages_sent": used_pages,
        "usage": usage_dict,
        "result": parsed.model_dump(),
    }

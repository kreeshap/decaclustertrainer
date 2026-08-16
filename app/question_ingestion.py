"""Deterministic text-layer PDF question extraction and duplicate detection."""

from __future__ import annotations

from difflib import SequenceMatcher
import hashlib
import io
import re

import pdfplumber


QUESTION_START = re.compile(r"(?m)^\s*(\d{1,3})[.)]\s+(.+)")
CHOICE = re.compile(r"(?ms)^\s*([A-D])[.)]\s+(.+?)(?=^\s*[A-D][.)]\s+|\Z)")
ANSWER_PAIR = re.compile(r"(?im)^\s*(\d{1,3})[.)]?\s*[-:]?\s*([A-D])\s*$")
KPI = re.compile(r"\b([A-Z]{2,4}:\d{3})\b")
SOURCE_LINE = re.compile(r"(?im)^\s*SOURCE:\s*(.+?)\s*$")


def normalize_question(text: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9\s]", " ", text.lower()).split())


def question_hash(text: str) -> str:
    return hashlib.sha256(normalize_question(text).encode("utf-8")).hexdigest()


def _clean(text: str) -> str:
    return " ".join((text or "").replace("\u00a0", " ").split())


def extract_pdf_questions(file_bytes: bytes) -> tuple[list[dict], dict]:
    pages: list[str] = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            pages.append(page.extract_text(x_tolerance=2, y_tolerance=3) or "")
    if not pages or sum(len(page.strip()) for page in pages) < 200:
        raise ValueError("Scanned or image-only PDF detected. V1 accepts PDFs with selectable text only.")

    full_text = "\n".join(pages)
    answer_matches = list(ANSWER_PAIR.finditer(full_text))
    answer_candidates = {int(match.group(1)): ord(match.group(2).upper()) - 65 for match in answer_matches}
    answer_details = {}
    for index, match in enumerate(answer_matches):
        tail = full_text[match.end(): answer_matches[index + 1].start() if index + 1 < len(answer_matches) else len(full_text)]
        source_lines = SOURCE_LINE.findall(tail)
        kpi_source = next((value.strip() for value in source_lines if re.fullmatch(r"[A-Z]{2,4}:\d{3}", value.strip())), "")
        if not kpi_source:
            inline_kpi = KPI.search(tail)
            kpi_source = inline_kpi.group(1) if inline_kpi else ""
        first_source = SOURCE_LINE.search(tail)
        explanation = _clean(tail[:first_source.start()] if first_source else tail)
        answer_details[int(match.group(1))] = {
            "kpi_code": kpi_source,
            "explanation": explanation[:4000] if len(explanation) >= 20 else "",
            "source_references": [value.strip() for value in source_lines if value.strip() != kpi_source],
            "raw_descriptive_key": _clean(f"{match.group(1)}. {match.group(2)} {tail}")[:8000],
        }
    starts = list(QUESTION_START.finditer(full_text))
    questions: list[dict] = []
    for index, match in enumerate(starts):
        number = int(match.group(1))
        block = full_text[match.start(): starts[index + 1].start() if index + 1 < len(starts) else len(full_text)]
        choices = CHOICE.findall(block)
        if len(choices) < 2:
            continue
        first_choice = re.search(r"(?m)^\s*A[.)]\s+", block)
        stem_block = block[match.end():first_choice.start()] if first_choice else ""
        stem = _clean(f"{match.group(2)} {stem_block}")
        choice_map = {label: _clean(value) for label, value in choices[:4]}
        ordered = [choice_map.get(label, "") for label in "ABCD"]
        page_number = next((i + 1 for i, page in enumerate(pages) if re.search(rf"(?m)^\s*{number}[.)]\s+", page)), None)
        kpi_match = KPI.search(block)
        details = answer_details.get(number, {})
        questions.append({
            "question_number": number, "page_number": page_number, "question_text": stem,
            "choices": ordered, "correct_index": answer_candidates.get(number),
            "explanation": details.get("explanation", ""),
            "kpi_code": (kpi_match.group(1) if kpi_match else details.get("kpi_code", "")),
            "source_references": details.get("source_references", []),
            "raw_descriptive_key": details.get("raw_descriptive_key", ""),
            "normalized_hash": question_hash(stem),
        })
    if not questions:
        raise ValueError("No numbered questions with answer choices were detected.")
    return questions, {"page_count": len(pages), "answer_keys_detected": len(answer_candidates)}


def assess_item(item: dict, existing: list[dict], prior: list[dict], reusable: bool) -> dict:
    reasons: list[str] = []
    if len(item["choices"]) != 4 or any(not choice for choice in item["choices"]):
        reasons.append("choices_incomplete")
    if item.get("correct_index") not in range(4):
        reasons.append("answer_key_missing")
    if not item.get("kpi_code"):
        reasons.append("kpi_missing")
    if not reusable:
        reasons.append("reference_only")
    duplicate_id = None
    similarity = 0.0
    candidates = existing + prior
    for candidate in candidates:
        if candidate.get("normalized_hash") == item["normalized_hash"]:
            duplicate_id = candidate.get("id")
            similarity = 1.0
            reasons.append("exact_duplicate")
            break
        score = SequenceMatcher(None, normalize_question(item["question_text"]), normalize_question(candidate.get("question_text", ""))).ratio()
        if score > similarity:
            similarity, duplicate_id = score, candidate.get("id")
    if similarity >= 0.90 and "exact_duplicate" not in reasons:
        reasons.append("near_duplicate")
    return {**item, "review_reasons": reasons, "duplicate_question_id": duplicate_id,
            "similarity": round(similarity, 4), "review_status": "ready" if not reasons else "pending"}


def build_style_profile(items: list[dict]) -> dict:
    """Extract non-expressive aggregate patterns; source wording is not returned."""
    if not items:
        return {"corpus_size": 0}
    stems = [str(item.get("question_text") or "") for item in items]
    word_counts = [len(stem.split()) for stem in stems]
    scenario_markers = ("company", "business", "manager", "customer", "employee", "client", "retailer")
    scenario_count = sum(any(marker in stem.lower() for marker in scenario_markers) for stem in stems)
    negative_count = sum(any(marker in stem.lower() for marker in (" not ", " except", "least likely")) for stem in stems)
    correct_positions = [item.get("correct_index") for item in items if item.get("correct_index") in range(4)]
    return {
        "corpus_size": len(items),
        "average_stem_words": round(sum(word_counts) / len(word_counts), 1),
        "stem_word_range": [min(word_counts), max(word_counts)],
        "scenario_percentage": round(100 * scenario_count / len(items)),
        "negative_wording_percentage": round(100 * negative_count / len(items)),
        "correct_position_distribution": [correct_positions.count(index) for index in range(4)],
        "required_choices": 4,
    }


def max_similarity(question_text: str, corpus: list[dict]) -> float:
    normalized = normalize_question(question_text)
    return max((SequenceMatcher(None, normalized, normalize_question(item.get("question_text", ""))).ratio()
                for item in corpus), default=0.0)


def parse_reference_citation(raw: str) -> dict:
    citation = _clean(raw)
    pages_match = re.search(r"\[?\bpp?\.\s*([^\]]+?)(?:\]|\.|$)", citation, re.I)
    pages = _clean(pages_match.group(1)) if pages_match else ""
    without_pages = re.sub(r"\[?\bpp?\.\s*[^\]]+?(?:\]|\.|$)", " ", citation, flags=re.I)
    year_match = re.search(r"\((19|20)\d{2}\)", without_pages)
    year = int(year_match.group(0)[1:-1]) if year_match else None
    authors = _clean(without_pages[:year_match.start()].rstrip(" .,")) if year_match else ""
    after_year = without_pages[year_match.end():].strip(" .") if year_match else without_pages
    edition_match = re.search(r"\(([^)]*\bed\.)\)", after_year, re.I)
    edition = _clean(edition_match.group(1)) if edition_match else ""
    title_part = after_year[:edition_match.start()] if edition_match else after_year
    title = _clean(title_part.strip(" ."))
    publisher = ""
    if edition_match:
        publisher = _clean(after_year[edition_match.end():].strip(" ."))
    canonical_text = re.sub(r"[^a-z0-9\s]", " ", without_pages.lower())
    canonical_key = hashlib.sha256(" ".join(canonical_text.split()).encode("utf-8")).hexdigest()
    search_query = " ".join(part for part in (f'"{title}"' if title else "", authors, edition) if part)
    return {"canonical_key": canonical_key, "title": title, "authors": authors, "edition": edition,
            "publication_year": year, "publisher": publisher, "raw_citation": citation,
            "pages": pages, "search_query": search_query or citation}

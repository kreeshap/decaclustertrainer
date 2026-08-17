"""Extract the normalized 2026-27 Finance curriculum from the official DECA PDF.

Usage:
    python scripts/extract_finance_curriculum.py path/to/2026-27-HS-DECA-Finance.pdf
"""

from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

import pdfplumber


ROOT = Path(__file__).resolve().parents[1]
FINANCE_DIR = ROOT / "performance indicator jsons" / "finance"
CURRICULUM_DIR = FINANCE_DIR / "curriculum"
EVENTS_DIR = FINANCE_DIR / "events"
SOURCE_DIR = FINANCE_DIR / "source"
SHARED_CORE = ROOT / "performance indicator jsons" / "shared" / "business_administration_core_2026_27.json"
DOCUMENT_ID = "2026-27-HS-DECA-Finance"
YEAR = "2026-27"

INDICATOR_RE = re.compile(r"^(.*?)\s+\(([A-Z]{2}:\d{3})\)\s+\((PQ|CS|SP|SU|MN|ON)\)$")


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("\ufffd", "'").replace("\u2018", "'").replace("\u2019", "'").replace("\u201c", '"').replace("\u201d", '"')).strip()


def page_lines(page) -> list[str]:
    lines = (page.extract_text() or "").splitlines()
    result = []
    for line in lines:
        line = clean(line)
        if not line or re.fullmatch(r"Page \d+", line):
            continue
        if ("Cluster for 2026-2027 HS DECA Exams" in line
                or line.startswith("Entrepreneurship (CS, SP, SU, MN, ON)")
                or line.startswith("Copyright ")):
            continue
        if line.endswith((" Core", " Pathway")):
            continue
        result.append(line)
    return result


def extract_section(
    pdf, pages: range, tier: int, curriculum_id: str, label: str,
    pathway: str | None, *, cluster: str = "Finance", document_id: str = DOCUMENT_ID,
    curriculum_section: str | None = None,
) -> dict:
    indicators = []
    area_code = area_name = standard = element = None
    pending_kind = None
    pending = ""

    def commit_pending() -> None:
        nonlocal area_code, area_name, standard, element, pending_kind, pending
        value = clean(pending)
        if pending_kind == "standard":
            standard = value
        elif pending_kind == "element":
            element = value
        pending_kind = None
        pending = ""

    for page_number in pages:
        lines = page_lines(pdf.pages[page_number - 1])
        i = 0
        while i < len(lines):
            line = lines[i]
            if line.startswith("Instructional Area: "):
                commit_pending()
                match = re.match(r"Instructional Area: (.*?) \(([A-Z]{2})\)$", line)
                if not match:
                    raise ValueError(f"Page {page_number}: malformed instructional area: {line}")
                area_name, area_code = match.group(1), match.group(2)
                standard = element = None
            elif line.startswith("Standard: "):
                commit_pending()
                pending_kind, pending = "standard", line.removeprefix("Standard: ")
            elif line.startswith("Performance Element: "):
                commit_pending()
                pending_kind, pending = "element", line.removeprefix("Performance Element: ")
            elif line == "Performance Indicators:":
                commit_pending()
            else:
                candidate = line
                j = i
                match = INDICATOR_RE.match(candidate)
                while not match and j + 1 < len(lines):
                    next_line = lines[j + 1]
                    if next_line.startswith(("Instructional Area:", "Standard:", "Performance Element:", "Performance Indicators:")):
                        break
                    candidate = clean(candidate + " " + next_line)
                    j += 1
                    match = INDICATOR_RE.match(candidate)
                if match:
                    commit_pending()
                    if not all((area_code, area_name, standard, element)):
                        raise ValueError(f"Page {page_number}: indicator lacks context: {candidate}")
                    official_text, code, level = match.groups()
                    indicators.append({
                        "code": code,
                        "level": level,
                        "official_text": official_text,
                        "display_text": official_text,
                        "text": official_text,
                        "tier": tier,
                        "curriculum_section": curriculum_section or label,
                        "cluster": cluster,
                        "pathway": pathway,
                        "instructional_area_code": area_code,
                        "instructional_area_name": area_name,
                        "standard": standard,
                        "performance_element": element,
                        "source": {
                            "competitive_year": YEAR,
                            "document": document_id,
                            "page": page_number,
                        },
                    })
                    i = j
                elif pending_kind:
                    pending = clean(pending + " " + line)
                else:
                    raise ValueError(f"Page {page_number}: unrecognized line: {line}")
            i += 1
    commit_pending()
    return {
        "schema_version": 1,
        "curriculum_id": curriculum_id,
        "name": label,
        "cluster": cluster,
        "tier": tier,
        "curriculum_section": curriculum_section or label,
        "pathway": pathway,
        "source": {"competitive_year": YEAR, "document": document_id, "pages": [pages.start, pages.stop - 1]},
        "performance_indicators": indicators,
    }


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Pass the official 2026-27 Finance PDF path")
    source = Path(sys.argv[1]).resolve()
    if not source.is_file():
        raise SystemExit(f"PDF not found: {source}")

    with pdfplumber.open(source) as pdf:
        datasets = [
            ("tier1_business_admin.json", extract_section(pdf, range(4, 21), 1, "business_administration_core_2026_27", "Business Administration Core", None)),
            ("tier2_finance.json", extract_section(pdf, range(21, 24), 2, "finance_tier2", "Finance Career Cluster", None)),
            ("tier3_accounting.json", extract_section(pdf, range(24, 30), 3, "finance_tier3_accounting", "Accounting Pathway", "Accounting")),
            ("tier3_corporate_finance.json", extract_section(pdf, range(34, 39), 3, "finance_tier3_corporate_finance", "Corporate Finance Pathway", "Corporate Finance")),
        ]

    expected = {
        "business_administration_core_2026_27": 367,
        "finance_tier2": 41,
        "finance_tier3_accounting": 109,
        "finance_tier3_corporate_finance": 92,
    }
    actual = {data["curriculum_id"]: len(data["performance_indicators"]) for _, data in datasets}
    if actual != expected:
        raise ValueError(f"Official count check failed: expected {expected}, got {actual}")

    for indicator in datasets[0][1]["performance_indicators"]:
        indicator["sources"] = [dict(indicator["source"])]
    write_json(SHARED_CORE, datasets[0][1])
    for filename, data in datasets[1:]:
        write_json(CURRICULUM_DIR / filename, data)

    event_defs = {
        "ACT.json": {
            "event_id": "accounting_application_series", "event_code": "ACT", "name": "Accounting Application Series",
            "event_type": "individual_series", "exam": {"curriculum": ["business_administration_core_2026_27", "finance_tier2"]},
            "roleplay": {"curriculum": ["business_administration_core_2026_27", "finance_tier2", "finance_tier3_accounting"]},
            "curriculum_usage": {"exam": {"curriculum": ["business_administration_core_2026_27", "finance_tier2"]}, "roleplay": {"curriculum": ["business_administration_core_2026_27", "finance_tier2", "finance_tier3_accounting"]}},
            "study_curriculum": ["business_administration_core_2026_27", "finance_tier2", "finance_tier3_accounting"],
        },
        "BFS.json": {
            "event_id": "business_finance_series", "event_code": "BFS", "name": "Business Finance Series",
            "event_type": "individual_series", "exam": {"curriculum": ["business_administration_core_2026_27", "finance_tier2"]},
            "roleplay": {"curriculum": ["business_administration_core_2026_27", "finance_tier2", "finance_tier3_corporate_finance"]},
            "curriculum_usage": {"exam": {"curriculum": ["business_administration_core_2026_27", "finance_tier2"]}, "roleplay": {"curriculum": ["business_administration_core_2026_27", "finance_tier2", "finance_tier3_corporate_finance"]}},
            "study_curriculum": ["business_administration_core_2026_27", "finance_tier2", "finance_tier3_corporate_finance"],
        },
        "FTDM.json": {
            "event_id": "financial_services_tdm", "event_code": "FTDM", "name": "Financial Services Team Decision Making",
            "event_type": "team_decision_making", "exam": {"curriculum": ["business_administration_core_2026_27", "finance_tier2"]},
            "case_study": {"curriculum": ["business_administration_core_2026_27", "finance_tier2"]},
            "curriculum_usage": {"exam": {"curriculum": ["business_administration_core_2026_27", "finance_tier2"]}, "case_study": {"curriculum": ["business_administration_core_2026_27", "finance_tier2"]}},
            "study_curriculum": ["business_administration_core_2026_27", "finance_tier2"],
        },
    }
    district_focus = {
        "competitive_year": YEAR,
        "status": "pending",
        "released_at": None,
        "instructional_areas": [],
    }
    for filename, data in event_defs.items():
        write_json(EVENTS_DIR / filename, {
            "schema_version": 1, "cluster": "Finance",
            "competitive_year": YEAR, "district_focus": district_focus, **data,
        })

    manifest = {
        "schema_version": 1,
        "cluster": "Finance",
        "competitive_year": YEAR,
        "source_document": f"source/{DOCUMENT_ID}.pdf",
        "exam_blueprint": "exam_blueprint.json",
        "curriculum": ["../shared/business_administration_core_2026_27.json"] + [f"curriculum/{name}" for name, _ in datasets[1:]],
        "events": [f"events/{name}" for name in event_defs],
        "counts": {**actual, "tier1_and_tier2": 408},
    }
    write_json(FINANCE_DIR / "manifest.json", manifest)
    SOURCE_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, SOURCE_DIR / f"{DOCUMENT_ID}.pdf")
    print(json.dumps({"status": "ok", "counts": actual}, indent=2))


if __name__ == "__main__":
    main()

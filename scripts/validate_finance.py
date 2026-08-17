"""Fail if normalized Finance curriculum differs from its official source PDF."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pdfplumber

from extract_finance_curriculum import FINANCE_DIR, extract_section


SPECS = [
    ("../shared/business_administration_core_2026_27.json", range(4, 21), 1, "business_administration_core_2026_27", "Business Administration Core", None, 367),
    ("curriculum/tier2_finance.json", range(21, 24), 2, "finance_tier2", "Finance Career Cluster", None, 41),
    ("curriculum/tier3_accounting.json", range(24, 30), 3, "finance_tier3_accounting", "Accounting Pathway", "Accounting", 109),
    ("curriculum/tier3_corporate_finance.json", range(34, 39), 3, "finance_tier3_corporate_finance", "Corporate Finance Pathway", "Corporate Finance", 92),
]


def signature(item: dict) -> tuple:
    source = item["source"]
    return (
        item["code"], item["level"], item["official_text"], item["tier"],
        item["instructional_area_code"], item["instructional_area_name"],
        item["standard"], item["performance_element"], source["page"],
    )


def main() -> None:
    manifest = json.loads((FINANCE_DIR / "manifest.json").read_text(encoding="utf-8"))
    pdf_path = FINANCE_DIR / manifest["source_document"]
    failures = []
    with pdfplumber.open(pdf_path) as pdf:
        for relative, pages, tier, curriculum_id, label, pathway, expected_count in SPECS:
            stored = json.loads((FINANCE_DIR / relative).read_text(encoding="utf-8"))
            extracted = extract_section(pdf, pages, tier, curriculum_id, label, pathway)
            stored_items = stored["performance_indicators"]
            extracted_items = extracted["performance_indicators"]
            if len(stored_items) != expected_count:
                failures.append(f"{curriculum_id}: expected {expected_count}, stored {len(stored_items)}")
            if [signature(x) for x in stored_items] != [signature(x) for x in extracted_items]:
                failures.append(f"{curriculum_id}: code/level/text/context/source differs from PDF")

    combined = sum(len(json.loads((FINANCE_DIR / spec[0]).read_text(encoding="utf-8"))["performance_indicators"]) for spec in SPECS[:2])
    if combined != 408:
        failures.append(f"Tier 1+2 expected 408, got {combined}")
    if failures:
        raise SystemExit("Finance validation failed:\n- " + "\n- ".join(failures))
    print("Finance validation passed: 408 Tier 1+2, 109 Accounting, 92 Corporate Finance; all source fields match the PDF.")


if __name__ == "__main__":
    main()

"""Fail if normalized Marketing curriculum differs from its official PDF."""

from __future__ import annotations

import json

import pdfplumber

from extract_finance_curriculum import extract_section
from extract_marketing_curriculum import BASE, DOCUMENT_ID


SPECS = [
    ("../shared/business_administration_core_2026_27.json", range(4, 21), 1, "business_administration_core_2026_27", "Business Administration Core", None, 367),
    ("curriculum/tier2_marketing.json", range(21, 26), 2, "marketing_tier2", "Marketing Career Cluster", None, 83),
    ("curriculum/tier3_marketing_communications.json", range(26, 35), 3, "marketing_tier3_communications", "Marketing Communications Pathway", "Marketing Communications", 160),
    ("curriculum/tier3_marketing_management.json", range(35, 39), 3, "marketing_tier3_management", "Marketing Management Pathway", "Marketing Management", 61),
    ("curriculum/tier3_marketing_research.json", range(39, 43), 3, "marketing_tier3_research", "Marketing Research Pathway", "Marketing Research", 68),
    ("curriculum/tier3_merchandising.json", range(43, 49), 3, "marketing_tier3_merchandising", "Merchandising Pathway", "Merchandising", 126),
    ("curriculum/tier3_professional_selling.json", range(49, 52), 3, "marketing_tier3_professional_selling", "Professional Selling Pathway", "Professional Selling", 51),
]
FIELDS = ("code", "level", "official_text", "tier", "instructional_area_code", "instructional_area_name", "standard", "performance_element")


def main() -> None:
    manifest = json.loads((BASE / "manifest.json").read_text(encoding="utf-8"))
    failures = []
    with pdfplumber.open(BASE / manifest["source_document"]) as pdf:
        for relative, pages, tier, cid, label, pathway, count in SPECS:
            stored = json.loads((BASE / relative).read_text(encoding="utf-8"))["performance_indicators"]
            fresh = extract_section(pdf, pages, tier, cid, label, pathway, cluster="Marketing", document_id=DOCUMENT_ID)["performance_indicators"]
            if len(stored) != count:
                failures.append(f"{cid}: expected {count}, found {len(stored)}")
            if relative.startswith("../shared/"):
                stored_rows = [tuple(x[k] for k in FIELDS) for x in stored]
                fresh_rows = [tuple(x[k] for k in FIELDS) for x in fresh]
                marketing_pages = {
                    (x["code"], next((s["page"] for s in x.get("sources", []) if s["document"] == DOCUMENT_ID), None))
                    for x in stored
                }
                if any((x["code"], x["source"]["page"]) not in marketing_pages for x in fresh):
                    failures.append(f"{cid}: missing Marketing source-page provenance")
            else:
                stored_rows = [tuple(x[k] for k in FIELDS) + (x["source"]["page"],) for x in stored]
                fresh_rows = [tuple(x[k] for k in FIELDS) + (x["source"]["page"],) for x in fresh]
            if stored_rows != fresh_rows:
                failures.append(f"{cid}: differs from fresh PDF extraction")
    if failures:
        raise SystemExit("Marketing validation failed:\n- " + "\n- ".join(failures))
    print("Marketing validation passed: all 916 source records and hierarchy fields match the PDF.")


if __name__ == "__main__":
    main()

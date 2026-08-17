"""Extract normalized 2026-27 Marketing curriculum and component eligibility."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pdfplumber

from extract_finance_curriculum import ROOT, YEAR, extract_section, write_json


BASE = ROOT / "performance indicator jsons" / "marketing"
CURRICULUM = BASE / "curriculum"
EVENTS = BASE / "events"
SOURCE = BASE / "source"
DOCUMENT_ID = "2026-27-HS-DECA-Marketing"
SHARED_CORE = ROOT / "performance indicator jsons" / "shared" / "business_administration_core_2026_27.json"


def curriculum_usage(exam: list[str], performance: list[str] | None, component: str = "roleplay") -> dict:
    return {"exam": {"curriculum": exam}, component: None if performance is None else {"curriculum": performance}}


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Pass the official 2026-27 Marketing PDF path")
    source = Path(sys.argv[1]).resolve()
    specs = [
        ("tier1_business_admin.json", range(4, 21), 1, "business_administration_core_2026_27", "Business Administration Core", None),
        ("tier2_marketing.json", range(21, 26), 2, "marketing_tier2", "Marketing Career Cluster", None),
        ("tier3_marketing_communications.json", range(26, 35), 3, "marketing_tier3_communications", "Marketing Communications Pathway", "Marketing Communications"),
        ("tier3_marketing_management.json", range(35, 39), 3, "marketing_tier3_management", "Marketing Management Pathway", "Marketing Management"),
        ("tier3_marketing_research.json", range(39, 43), 3, "marketing_tier3_research", "Marketing Research Pathway", "Marketing Research"),
        ("tier3_merchandising.json", range(43, 49), 3, "marketing_tier3_merchandising", "Merchandising Pathway", "Merchandising"),
        ("tier3_professional_selling.json", range(49, 52), 3, "marketing_tier3_professional_selling", "Professional Selling Pathway", "Professional Selling"),
    ]
    with pdfplumber.open(source) as pdf:
        datasets = [
            (filename, extract_section(pdf, pages, tier, cid, label, pathway, cluster="Marketing", document_id=DOCUMENT_ID))
            for filename, pages, tier, cid, label, pathway in specs
        ]

    finance_core = json.loads(SHARED_CORE.read_text(encoding="utf-8")) if SHARED_CORE.exists() else None
    marketing_core = datasets[0][1]
    comparable = ("code", "level", "official_text", "instructional_area_code", "instructional_area_name", "standard", "performance_element")
    if finance_core:
        left = [{k: item[k] for k in comparable} for item in finance_core["performance_indicators"]]
        right = [{k: item[k] for k in comparable} for item in marketing_core["performance_indicators"]]
        if left != right:
            raise ValueError("Marketing Tier 1 is not field-for-field identical to the shared Finance core")
        for shared_item, marketing_item in zip(finance_core["performance_indicators"], marketing_core["performance_indicators"]):
            sources = shared_item.setdefault("sources", [dict(shared_item["source"])])
            marketing_source = dict(marketing_item["source"])
            if marketing_source not in sources:
                sources.append(marketing_source)
        write_json(SHARED_CORE, finance_core)
    else:
        write_json(SHARED_CORE, marketing_core)

    for filename, data in datasets[1:]:
        write_json(CURRICULUM / filename, data)

    core = "business_administration_core_2026_27"
    t2 = "marketing_tier2"
    shared = [core, t2]
    pathways = {
        "AAM": "marketing_tier3_merchandising",
        "ASM": "marketing_tier3_management",
        "BSM": "marketing_tier3_management",
        "FMS": "marketing_tier3_management",
        "MCS": "marketing_tier3_communications",
        "RMS": "marketing_tier3_merchandising",
        "SEM": "marketing_tier3_management",
    }
    names = {
        "AAM": "Apparel and Accessories Marketing Series", "ASM": "Automotive Services Marketing Series",
        "BSM": "Business Services Marketing Series", "FMS": "Food Marketing Series",
        "MCS": "Marketing Communications Series", "RMS": "Retail Merchandising Series",
        "SEM": "Sports and Entertainment Marketing Series",
    }
    event_defs = {}
    for code, pathway in pathways.items():
        event_defs[code] = {
            "name": names[code], "event_type": "individual_series",
            "curriculum_usage": curriculum_usage(shared, [*shared, pathway]),
            "study_curriculum": [*shared, pathway],
        }
    for code, name in {
        "BTDM": "Buying and Merchandising Team Decision Making",
        "MTDM": "Marketing Management Team Decision Making",
        "STDM": "Sports and Entertainment Marketing Team Decision Making",
    }.items():
        event_defs[code] = {
            "name": name, "event_type": "team_decision_making",
            "curriculum_usage": curriculum_usage(shared, shared, "case_study"), "study_curriculum": shared,
        }
    for code, name in {
        "IMCE": "Integrated Marketing Campaign-Event", "IMCP": "Integrated Marketing Campaign-Product",
        "IMCS": "Integrated Marketing Campaign-Service", "PSE": "Professional Selling",
    }.items():
        event_defs[code] = {
            "name": name, "event_type": "exam_only",
            "curriculum_usage": curriculum_usage(shared, None), "study_curriculum": shared,
        }
    event_defs["PMK"] = {
        "name": "Principles of Marketing", "event_type": "principles",
        "curriculum_usage": curriculum_usage([core], [core]), "study_curriculum": [core],
    }
    focus = {"competitive_year": YEAR, "status": "pending", "released_at": None, "instructional_areas": []}
    for code, event in event_defs.items():
        event_id = event["name"].lower().replace("-", "_").replace(" ", "_")
        write_json(EVENTS / f"{code}.json", {
            "schema_version": 1, "cluster": "Marketing", "competitive_year": YEAR,
            "event_id": event_id, "event_code": code, "district_focus": focus, **event,
        })

    paths = ["../shared/business_administration_core_2026_27.json"] + [f"curriculum/{name}" for name, _ in datasets[1:]]
    counts = {data["curriculum_id"]: len(data["performance_indicators"]) for _, data in datasets}
    write_json(BASE / "manifest.json", {
        "schema_version": 1, "cluster": "Marketing", "competitive_year": YEAR,
        "source_document": f"source/{DOCUMENT_ID}.pdf", "curriculum": paths,
        "exam_blueprint": "exam_blueprint.json",
        "events": [f"events/{code}.json" for code in event_defs], "counts": counts,
    })
    SOURCE.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, SOURCE / f"{DOCUMENT_ID}.pdf")
    print(json.dumps({"status": "ok", "counts": counts, "events": len(event_defs)}, indent=2))


if __name__ == "__main__":
    main()

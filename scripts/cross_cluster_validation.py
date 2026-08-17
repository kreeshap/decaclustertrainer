"""Validate normalized DECA curriculum manifests and event eligibility."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "performance indicator jsons"
VALID_LEVELS = {"PQ", "CS", "SP", "SU", "MN", "ON"}
EXPECTED = {
    "business_administration_core_2026_27": 367,
    "finance_tier2": 41,
    "finance_tier3_accounting": 109,
    "finance_tier3_corporate_finance": 92,
    "marketing_tier2": 83,
    "marketing_tier3_communications": 160,
    "marketing_tier3_management": 61,
    "marketing_tier3_research": 68,
    "marketing_tier3_merchandising": 126,
    "marketing_tier3_professional_selling": 51,
    "hospitality_tier2": 123,
    "hospitality_tier3_event_management": 127,
    "hospitality_tier3_lodging": 89,
    "hospitality_tier3_restaurant": 115,
    "hospitality_tier3_travel_tourism": 153,
    "bma_tier2": 54,
    "bma_tier3_administrative_services": 97,
    "bma_tier3_business_information_management": 74,
    "bma_tier3_general_management": 43,
    "bma_tier3_human_resources": 93,
    "bma_tier3_operations": 134,
    "entrepreneurship_business_administration_core": 175,
    "entrepreneurship_business_management_core": 14,
    "entrepreneurship_finance_core": 13,
    "entrepreneurship_marketing_core": 44,
}


def main() -> None:
    failures = []
    wording: dict[str, set[str]] = defaultdict(set)
    loaded: dict[str, dict] = {}
    manifests = [json.loads(p.read_text(encoding="utf-8")) | {"_base": p.parent} for p in DATA.glob("*/manifest.json")]
    for manifest in manifests:
        base = manifest["_base"]
        curricula = {}
        for relative in manifest["curriculum"]:
            data = json.loads((base / relative).read_text(encoding="utf-8"))
            cid = data["curriculum_id"]
            curricula[cid] = data
            loaded[cid] = data
            items = data.get("performance_indicators", [])
            if cid in EXPECTED and len(items) != EXPECTED[cid]:
                failures.append(f"{cid}: expected {EXPECTED[cid]} indicators, found {len(items)}")
            for item in items:
                wording[item["code"]].add(item["official_text"])
                if not item.get("performance_element"):
                    failures.append(f"{cid}/{item.get('code')}: missing Performance Element")
                if not item.get("source", {}).get("page"):
                    failures.append(f"{cid}/{item.get('code')}: missing source page")
                if item.get("level") not in VALID_LEVELS:
                    failures.append(f"{cid}/{item.get('code')}: invalid level {item.get('level')}")
                if item.get("source", {}).get("competitive_year") != manifest["competitive_year"]:
                    failures.append(f"{cid}/{item.get('code')}: source year mismatch")
                if manifest.get("curriculum_family") == "sectioned":
                    if item.get("tier") is not None or not item.get("curriculum_section"):
                        failures.append(f"{cid}/{item.get('code')}: sectioned curriculum must have null tier and official curriculum_section")
        for relative in manifest["events"]:
            event = json.loads((base / relative).read_text(encoding="utf-8"))
            if event.get("competitive_year") != manifest["competitive_year"]:
                failures.append(f"{event.get('event_code')}: event year mismatch")
            for component, usage in event.get("curriculum_usage", {}).items():
                if usage is None:
                    continue
                for cid in usage.get("curriculum", []):
                    if cid not in curricula:
                        failures.append(f"{event.get('event_code')}/{component}: missing curriculum {cid}")
            for cid in event.get("study_curriculum", []):
                if cid not in curricula:
                    failures.append(f"{event.get('event_code')}: missing study curriculum {cid}")

    for code, versions in wording.items():
        if len(versions) > 1:
            failures.append(f"{code}: conflicting official wording: {sorted(versions)}")
    missing_expected = set(EXPECTED) - set(loaded)
    if missing_expected:
        failures.append(f"missing expected curricula: {sorted(missing_expected)}")

    for blueprint_file in DATA.glob("*/exam_blueprint.json"):
        blueprint = json.loads(blueprint_file.read_text(encoding="utf-8"))
        for stage in ("district", "association", "icdc"):
            total = sum(row[stage] for row in blueprint["instructional_areas"])
            if total != blueprint["item_count"]:
                failures.append(f"{blueprint['exam']} blueprint {stage} totals {total}, expected {blueprint['item_count']}")
    if failures:
        raise SystemExit("Curriculum integrity failed:\n- " + "\n- ".join(failures))
    print(f"Curriculum integrity passed: {len(loaded)} curricula, {len(wording)} unique PI codes, all event/component references valid.")


if __name__ == "__main__":
    main()

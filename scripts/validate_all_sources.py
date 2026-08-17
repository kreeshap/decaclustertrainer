"""Compare every normalized curriculum against a fresh extraction of its PDF."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pdfplumber

sys.path.insert(0, str(Path(__file__).resolve().parent))
from extract_finance_curriculum import ROOT, extract_section  # noqa: E402


FIELDS = ("code", "level", "official_text", "tier", "curriculum_section", "instructional_area_code", "instructional_area_name", "standard", "performance_element", "pathway")


def row(item):
    return tuple(item.get(field) for field in FIELDS)


def main() -> None:
    failures = []
    data_dir = ROOT / "performance indicator jsons"
    for manifest_file in data_dir.glob("*/manifest.json"):
        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
        base = manifest_file.parent
        pdf_path = base / manifest["source_document"]
        document_id = pdf_path.stem
        with pdfplumber.open(pdf_path) as pdf:
            for relative in manifest["curriculum"]:
                stored_data = json.loads((base / relative).read_text(encoding="utf-8"))
                source_pages = stored_data["source"]["pages"]
                fresh_data = extract_section(
                    pdf, range(source_pages[0], source_pages[1] + 1), stored_data.get("tier"),
                    stored_data["curriculum_id"], stored_data["name"], stored_data.get("pathway"),
                    cluster=manifest["cluster"], document_id=document_id,
                    curriculum_section=stored_data.get("curriculum_section"),
                )
                stored = stored_data["performance_indicators"]
                fresh = fresh_data["performance_indicators"]
                if [row(x) for x in stored] != [row(x) for x in fresh]:
                    failures.append(f"{manifest['cluster']}/{stored_data['curriculum_id']}: hierarchy or PI data differs from PDF")
                    continue
                for item in fresh:
                    stored_item = next(x for x in stored if x["code"] == item["code"])
                    if relative.startswith("../shared/"):
                        if item["source"] not in stored_item.get("sources", []):
                            failures.append(f"{manifest['cluster']}/{item['code']}: shared provenance page missing")
                    elif item["source"] != stored_item["source"]:
                        failures.append(f"{manifest['cluster']}/{item['code']}: source page differs")
    if failures:
        raise SystemExit("Fresh source validation failed:\n- " + "\n- ".join(failures))
    print("Fresh source validation passed for every curriculum in all five source PDFs.")


if __name__ == "__main__":
    main()

"""Contract tests for component-specific student curriculum experiences."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.learn_helpers import _load_all_kpis


def main() -> None:
    kpis, events = _load_all_kpis(force_reload=True)
    event_by_code = {event["event_code"]: event["id"] for event in events}

    def rows(code):
        return [k for k in kpis if k["event"] == event_by_code[code]]

    def eligible(code, component):
        return [k for k in rows(code) if component in k.get("eligible_components", [])]

    assert len(eligible("ACT", "exam")) == 408
    assert len(eligible("ACT", "roleplay")) == 517
    assert any(k.get("pathway") == "Accounting" for k in eligible("ACT", "roleplay"))
    assert not any(k.get("tier") == "Tier 3" for k in eligible("ACT", "exam"))

    assert any(k.get("pathway") == "Marketing Communications" for k in eligible("MCS", "roleplay"))
    assert not any(k.get("tier") == "Tier 3" for k in eligible("FTDM", "case_study"))
    assert not eligible("IMCP", "roleplay")

    assert any(k.get("pathway") == "Lodging" for k in eligible("HLM", "roleplay"))
    assert not any(k.get("tier") == "Tier 3" for k in eligible("HTDM", "case_study"))
    assert any(k.get("pathway") == "Human Resources Management" for k in eligible("HRM", "roleplay"))
    assert not any(k.get("tier") == "Tier 3" for k in eligible("BLTDM", "case_study"))

    for code in ("ENT", "ETDM"):
        assert rows(code) and all(k.get("tier") is None and k.get("curriculum_section") for k in rows(code))
    print("Student curriculum experience tests passed.")


if __name__ == "__main__":
    main()

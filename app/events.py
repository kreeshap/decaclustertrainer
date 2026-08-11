"""Canonical event identities for the Phase 0 beta."""

BETA_EVENTS = {
    "accounting_application_series": {"name": "Accounting Application Series", "cluster": "Finance"},
    "business_finance_series": {"name": "Business Finance Series", "cluster": "Finance"},
    "financial_services_tdm": {"name": "Financial Services Team Decision Making", "cluster": "Finance"},
}

_ALIASES = {"financial_services_team_decision_making": "financial_services_tdm"}


def canonical_event_id(value: object) -> str:
    """Return a supported canonical event id, or an empty string."""
    raw = str(value or "").strip()
    slug = _ALIASES.get(raw.lower().replace(" ", "_"), raw.lower().replace(" ", "_"))
    if slug in BETA_EVENTS:
        return slug
    for event_id, event in BETA_EVENTS.items():
        if raw.casefold() == event["name"].casefold():
            return event_id
    return ""


def beta_event(event_id: object) -> dict | None:
    return BETA_EVENTS.get(canonical_event_id(event_id))

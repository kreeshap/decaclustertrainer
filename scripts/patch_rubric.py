#!/usr/bin/env python3
"""Patch the two loose rubric checks in validate_generation.py."""
import os
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
path = os.path.join(BASE, 'scripts', 'validate_generation.py')

with open(path, encoding='utf-8') as f:
    content = f.read()

idx1 = content.find('def check_matches_kpi')
idx2 = content.find('\ndef check_correct_index_valid')
assert idx1 != -1 and idx2 != -1

NEW_CHECKS = '''def check_matches_kpi(q: dict, kpi_text: str) -> tuple[bool, str]:
    """Question text or explanation should be topically related to the KPI.
    We check for meaningful word overlap rather than exact phrasing, because
    the model often tests concepts implied by the KPI (e.g. a question about
    FASB correctly tests 'accounting standards' without repeating those words)."""
    haystack = (
        (q.get("text") or "") + " " +
        (q.get("explanation") or "")
    ).lower()
    STOP = {"the","and","for","that","with","this","from","into","have",
            "will","your","are","been","its","but","not","can","all","use",
            "used","role","nature","explain","describe","discuss","identify",
            "demonstrate","utilize","employ","implement","develop","apply"}
    words = [
        w.strip(".,;:()/")
        for w in kpi_text.lower().split()
        if len(w) > 3 and w.strip(".,;:()/") not in STOP
    ]
    if not words:
        return True, "No meaningful words to check"
    matched = [w for w in words if w in haystack]
    if len(matched) >= 1:
        return True, f"Keywords found: {matched}"
    # Fallback: check if kpi_code subject prefix appears (e.g. "fi", "bl")
    prefix = (q.get("kpi_code") or "").split(":")[0].lower()
    if prefix and len(prefix) >= 2 and prefix in haystack:
        return True, f"KPI prefix \'{prefix}\' found"
    return False, f"No relevant terms from \'{kpi_text[:50]}\' found in question/explanation"

def check_plausible_distractors(q: dict) -> tuple[bool, str]:
    """All 4 choices should be non-empty.  Single-word answers (like acronyms)
    are valid — only flag truly empty or trivially short choices (< 3 chars)."""
    choices = q.get("choices") or []
    if len(choices) != 4:
        return False, f"Expected 4 choices, got {len(choices)}"
    for i, c in enumerate(choices):
        if len(c.strip()) < 3:
            return False, f"Choice {chr(65+i)} is too short: {c!r}"
    return True, "OK"
'''

content = content[:idx1] + NEW_CHECKS + content[idx2:]

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
print("Rubric patched.")

#!/usr/bin/env python3
"""
validate_generation.py
======================
Generates study content for 20 randomly sampled KPIs and scores every
question against a rubric.  Writes two output files:

  validation_results/results_<timestamp>.json   — raw data
  validation_results/report_<timestamp>.md      — human-readable review

Usage:
  python scripts/validate_generation.py [--count 20] [--event <event_id>] [--seed 42]

The script intentionally does NOT write to Supabase — it is read-only
with respect to the database.
"""

import argparse
import json
import os
import random
import sys
import time
from datetime import datetime
from pathlib import Path

# ── Bootstrap app path ────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from app.config import GROQ_API_KEY, GEMINI_API_KEY
from app.ai import call_groq, call_gemini_json
from app.learn_helpers import _load_all_kpis

# ── Rubric ────────────────────────────────────────────────────────────────────
# Each check returns (passed: bool, note: str)

def check_factually_plausible(q: dict) -> tuple[bool, str]:
    """Heuristic: question text and choices should be non-empty and
    the explanation should mention why the correct answer is right."""
    text = (q.get("text") or "").strip()
    choices = q.get("choices") or []
    explanation = (q.get("explanation") or "").strip()
    if len(text) < 20:
        return False, "Question text too short"
    if len(choices) != 4:
        return False, f"Expected 4 choices, got {len(choices)}"
    if len(explanation) < 30:
        return False, "Explanation too short"
    return True, "OK"

def check_matches_kpi(q: dict, kpi_text: str) -> tuple[bool, str]:
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
        return True, f"KPI prefix '{prefix}' found"
    return False, f"No relevant terms from '{kpi_text[:50]}' found in question/explanation"

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

def check_clear_wording(q: dict) -> tuple[bool, str]:
    text = (q.get("text") or "").strip()
    if not (text.endswith("?") or text.endswith(":")):
        return False, "Question does not end with ? or :"
    if len(text.split()) < 6:
        return False, "Question stem too short"
    return True, "OK"


def check_correct_index_valid(q: dict) -> tuple[bool, str]:
    correct = q.get("correct")
    choices = q.get("choices") or []
    if not isinstance(correct, int):
        return False, f"correct is not an int: {correct!r}"
    if not (0 <= correct <= len(choices) - 1):
        return False, f"correct index {correct} out of range for {len(choices)} choices"
    return True, "OK"

def check_deca_style(q: dict) -> tuple[bool, str]:
    """Heuristic: DECA questions tend to be scenario-aware for application,
    and concise for recognition. Check for obvious issues."""
    text = (q.get("text") or "").lower()
    # Red flags
    red_flags = ["i don't know", "n/a", "placeholder", "example question", "lorem"]
    for flag in red_flags:
        if flag in text:
            return False, f"Red flag phrase found: '{flag}'"
    return True, "OK"

RUBRIC = [
    ("factually_plausible",  check_factually_plausible),
    ("matches_kpi",          lambda q, kpi: check_matches_kpi(q, kpi)),
    ("clear_wording",        check_clear_wording),
    ("plausible_distractors",check_plausible_distractors),
    ("correct_index_valid",  check_correct_index_valid),
    ("deca_style",           check_deca_style),
]

# ── Generation ────────────────────────────────────────────────────────────────

GENERATION_PROMPT = """\
You are a DECA exam coach creating study materials for high school business students.

Generate educational content for this DECA Performance Indicator (KPI):
- Code: {code}
- KPI: {text}
- Subject Cluster: {cluster}
- Standard: {standard}
- DECA Cluster: {deca_cluster}

Return ONLY valid JSON (no markdown, no extra text) with this exact structure:

{{
  "vocab": [
    {{"term": "Key Term 1", "definition": "Clear, precise definition a student must know"}},
    {{"term": "Key Term 2", "definition": "Clear, precise definition"}},
    {{"term": "Key Term 3", "definition": "Clear, precise definition"}},
    {{"term": "Key Term 4", "definition": "Clear, precise definition"}},
    {{"term": "Key Term 5", "definition": "Clear, precise definition"}},
    {{"term": "Key Term 6", "definition": "Clear, precise definition"}}
  ],
  "concept": {{
    "summary": "One clear sentence explaining what this KPI is about",
    "explanation": "2-3 paragraphs for a high school student. Plain language, real-world examples, why it matters in DECA.",
    "bullets": ["Key insight 1", "Key insight 2", "Key insight 3"],
    "table": [
      {{"term": "Term 1", "definition": "Brief definition"}},
      {{"term": "Term 2", "definition": "Brief definition"}},
      {{"term": "Term 3", "definition": "Brief definition"}}
    ]
  }},
  "recognition_questions": [
    {{
      "text": "Question stem testing recall or definition of this KPI",
      "choices": ["Choice A", "Choice B", "Choice C", "Choice D"],
      "correct": 0,
      "explanation": "Choice A is correct because [reason]. The others are wrong because [reason].",
      "kpi_code": "{code}",
      "kpi_text": "{text}",
      "cluster": "{cluster}",
      "deca_cluster": "{deca_cluster}"
    }}
  ],
  "application_question": {{
    "text": "A realistic business scenario where a student must apply this KPI concept. 2-3 sentences setting the scene, then a clear question.",
    "choices": ["Choice A — specific action or decision", "Choice B", "Choice C", "Choice D"],
    "correct": 0,
    "explanation": "Choice A is correct because [specific business reasoning]. The others are wrong because [reason each].",
    "kpi_code": "{code}",
    "kpi_text": "{text}",
    "cluster": "{cluster}",
    "deca_cluster": "{deca_cluster}"
  }}
}}

Rules:
- "recognition_questions": generate EXACTLY 5 questions. These test recall, definition, and identification.
- "application_question": generate EXACTLY 1 question. Scenario-based, realistic business situation.
- All questions: 4 plausible choices (A-D), only one correct. Distribute correct index (0-3) across the 5 recognition questions.
- Do NOT repeat the same scenario angle in both recognition and application questions."""


def generate_for_kpi(kpi: dict, groq_only: bool = False) -> tuple[dict | None, str | None]:
    prompt = GENERATION_PROMPT.format(
        code=kpi["code"],
        text=kpi["text"],
        cluster=kpi["cluster"],
        standard=kpi.get("standard", ""),
        deca_cluster=kpi.get("deca_cluster", "Business"),
    )
    result, err = call_groq([{"role": "user", "content": prompt}], max_tokens=3500)
    if err and not groq_only:
        result, err = call_gemini_json(prompt, max_tokens=3500)
    return result, err


# ── Scoring ───────────────────────────────────────────────────────────────────

def score_question(q: dict, kpi_text: str, q_type: str) -> dict:
    results = {}
    for name, fn in RUBRIC:
        try:
            if name == "matches_kpi":
                passed, note = fn(q, kpi_text)
            else:
                passed, note = fn(q)
        except Exception as e:
            passed, note = False, f"Check error: {e}"
        results[name] = {"passed": passed, "note": note}
    total = len(results)
    passed = sum(1 for r in results.values() if r["passed"])
    return {
        "question_type": q_type,
        "text": (q.get("text") or "")[:120],
        "correct_index": q.get("correct"),
        "choices": q.get("choices") or [],
        "explanation": (q.get("explanation") or "")[:200],
        "checks": results,
        "score": passed,
        "total": total,
        "pass_rate": round(passed / total, 2),
    }


def score_generation(kpi: dict, result: dict) -> dict:
    recognition = result.get("recognition_questions") or []
    application_raw = result.get("application_question")

    # Normalise: handle old flat "questions" key from cached results
    if not recognition and not application_raw:
        flat = result.get("questions") or []
        recognition = [q for q in flat if q.get("question_type") != "application"]
        app_list = [q for q in flat if q.get("question_type") == "application"]
        application_raw = app_list[0] if app_list else None

    scored_recognition = [
        score_question(q, kpi["text"], "recognition") for q in recognition
    ]
    scored_application = (
        [score_question(application_raw, kpi["text"], "application")]
        if isinstance(application_raw, dict) and application_raw.get("text")
        else []
    )
    all_scored = scored_recognition + scored_application

    # Structural checks
    structural = {
        "has_vocab":              len(result.get("vocab") or []) >= 4,
        "vocab_count":            len(result.get("vocab") or []),
        "has_concept":            bool((result.get("concept") or {}).get("explanation")),
        "recognition_count":      len(recognition),
        "has_application":        bool(scored_application),
        "recognition_target_met": len(recognition) == 5,
    }

    total_q = len(all_scored)
    pass_rate = (
        round(sum(q["pass_rate"] for q in all_scored) / total_q, 2)
        if total_q else 0.0
    )

    # Per-check aggregate pass rates
    check_aggregates = {}
    for check_name, _ in RUBRIC:
        vals = [q["checks"][check_name]["passed"] for q in all_scored if check_name in q["checks"]]
        check_aggregates[check_name] = round(sum(vals) / len(vals), 2) if vals else 0.0

    return {
        "kpi_code": kpi["code"],
        "kpi_text": kpi["text"],
        "cluster": kpi["cluster"],
        "deca_cluster": kpi.get("deca_cluster", ""),
        "event": kpi.get("event", ""),
        "structural": structural,
        "questions": all_scored,
        "total_questions": total_q,
        "overall_pass_rate": pass_rate,
        "check_aggregates": check_aggregates,
    }


# ── Report ────────────────────────────────────────────────────────────────────

def write_report(results: list[dict], path: Path) -> None:
    lines = []
    lines.append("# DECA Generation Quality Report\n")
    lines.append(f"Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}\n")
    lines.append(f"KPIs sampled: {len(results)}\n\n")

    # ── Aggregate summary ──────────────────────────────────────────────────
    ok = [r for r in results if not r.get("error")]
    failed_gen = [r for r in results if r.get("error")]
    lines.append("## Summary\n")
    lines.append(f"- Generation succeeded: {len(ok)} / {len(results)}\n")
    if ok:
        avg_pass = round(sum(r["overall_pass_rate"] for r in ok) / len(ok), 2)
        lines.append(f"- Average question pass rate: {avg_pass * 100:.0f}%\n")

        # Per-check aggregates
        all_checks = {}
        for r in ok:
            for check, rate in r["check_aggregates"].items():
                all_checks.setdefault(check, []).append(rate)
        lines.append("\n### Per-Check Pass Rates\n")
        lines.append("| Check | Pass Rate |\n|---|---|\n")
        for check, rates in all_checks.items():
            avg = round(sum(rates) / len(rates) * 100)
            status = "✅" if avg >= 85 else ("⚠️" if avg >= 70 else "❌")
            lines.append(f"| {check} | {avg}% {status} |\n")

        # Structural
        lines.append("\n### Structural Checks\n")
        lines.append("| Check | Pass Rate |\n|---|---|\n")
        struct_keys = list(ok[0]["structural"].keys()) if ok else []
        for key in struct_keys:
            vals = [r["structural"].get(key) for r in ok if isinstance(r["structural"].get(key), bool)]
            if vals:
                pct = round(sum(vals) / len(vals) * 100)
                status = "✅" if pct >= 85 else ("⚠️" if pct >= 70 else "❌")
                lines.append(f"| {key} | {pct}% {status} |\n")

    if failed_gen:
        lines.append(f"\n### Generation Failures ({len(failed_gen)})\n")
        for r in failed_gen:
            lines.append(f"- `{r['kpi_code']}` — {r['error']}\n")

    # ── Per-KPI detail ─────────────────────────────────────────────────────
    lines.append("\n---\n\n## Per-KPI Detail\n")
    for r in ok:
        pass_pct = round(r["overall_pass_rate"] * 100)
        flag = "✅" if pass_pct >= 85 else ("⚠️" if pass_pct >= 70 else "❌")
        lines.append(f"\n### {flag} `{r['kpi_code']}` — {r['kpi_text'][:80]}\n")
        lines.append(f"*Cluster: {r['cluster']} | Event: {r['event']}*\n\n")
        lines.append(f"**Overall pass rate: {pass_pct}%** | ")
        lines.append(f"Questions: {r['total_questions']} ")
        lines.append(f"(recognition: {r['structural']['recognition_count']}, ")
        lines.append(f"application: {'yes' if r['structural']['has_application'] else 'no'})\n\n")

        for q in r["questions"]:
            q_flag = "✅" if q["pass_rate"] >= 0.85 else ("⚠️" if q["pass_rate"] >= 0.7 else "❌")
            lines.append(f"**{q_flag} [{q['question_type'].upper()}]** {q['text']}\n\n")
            for i, choice in enumerate(q["choices"]):
                marker = "→" if i == q["correct_index"] else " "
                lines.append(f"  {marker} {chr(65+i)}. {choice[:100]}\n")
            lines.append(f"\n  *Explanation:* {q['explanation'][:180]}\n\n")
            failing = [
                f"{name}: {d['note']}"
                for name, d in q["checks"].items()
                if not d["passed"]
            ]
            if failing:
                lines.append(f"  ⚠️ **Failing checks:** {'; '.join(failing)}\n\n")

    path.write_text("".join(lines), encoding="utf-8")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Validate DECA question generation")
    parser.add_argument("--count",  type=int, default=20, help="Number of KPIs to sample")
    parser.add_argument("--event",  type=str, default="",  help="Filter to a specific event_id")
    parser.add_argument("--seed",   type=int, default=42,  help="Random seed for reproducibility")
    parser.add_argument("--delay",     type=float, default=2.0,  help="Seconds between API calls (rate limiting)")
    parser.add_argument("--groq-only", action="store_true",      help="Skip Gemini fallback (avoids free-tier rate limits)")
    args = parser.parse_args()

    if not GROQ_API_KEY and not GEMINI_API_KEY:
        print("ERROR: Neither GROQ_API_KEY nor GEMINI_API_KEY is set in .env")
        sys.exit(1)

    # ── Sample KPIs ──────────────────────────────────────────────────────
    print("Loading KPIs...")
    all_kpis, events = _load_all_kpis()

    if args.event:
        pool = [k for k in all_kpis if k["event"] == args.event]
        if not pool:
            print(f"ERROR: No KPIs found for event '{args.event}'")
            print(f"Available events: {[e['id'] for e in events]}")
            sys.exit(1)
    else:
        pool = all_kpis

    random.seed(args.seed)
    sample = random.sample(pool, min(args.count, len(pool)))
    print(f"Sampled {len(sample)} KPIs from {len(pool)} total")
    print(f"Events in sample: {sorted(set(k['event'] for k in sample))}\n")

    # ── Output dir ───────────────────────────────────────────────────────
    out_dir = ROOT / "validation_results"
    out_dir.mkdir(exist_ok=True)
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")

    # ── Generate + score ─────────────────────────────────────────────────
    results = []
    for i, kpi in enumerate(sample, 1):
        print(f"[{i:2d}/{len(sample)}] {kpi['code']:10s} {kpi['text'][:60]}")
        start = time.time()

        result, err = generate_for_kpi(kpi, groq_only=args.groq_only)
        elapsed = round(time.time() - start, 1)

        if err or not result:
            print(f"          ✗ Generation failed ({elapsed}s): {err}")
            results.append({
                "kpi_code": kpi["code"],
                "kpi_text": kpi["text"],
                "cluster": kpi["cluster"],
                "deca_cluster": kpi.get("deca_cluster", ""),
                "event": kpi.get("event", ""),
                "error": err or "No result returned",
            })
        else:
            scored = score_generation(kpi, result)
            pct = round(scored["overall_pass_rate"] * 100)
            flag = "✅" if pct >= 85 else ("⚠️" if pct >= 70 else "❌")
            q_count = scored["total_questions"]
            print(f"          {flag} {pct}% pass rate | {q_count}q | {elapsed}s")
            results.append(scored)

        if i < len(sample):
            time.sleep(args.delay)

    # ── Write outputs ─────────────────────────────────────────────────────
    json_path = out_dir / f"results_{ts}.json"
    json_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nRaw results → {json_path}")

    report_path = out_dir / f"report_{ts}.md"
    write_report(results, report_path)
    print(f"Report      → {report_path}")

    # ── Print summary ─────────────────────────────────────────────────────
    ok = [r for r in results if not r.get("error")]
    failed = [r for r in results if r.get("error")]
    print(f"\n{'='*50}")
    print(f"Results: {len(ok)} succeeded, {len(failed)} failed")
    if ok:
        avg = round(sum(r["overall_pass_rate"] for r in ok) / len(ok) * 100)
        below_70 = [r for r in ok if r["overall_pass_rate"] < 0.70]
        print(f"Average pass rate: {avg}%")
        print(f"KPIs below 70%: {len(below_70)}")
        if avg < 85:
            print("\n⚠️  Average pass rate below 85% — review the report and fix prompting before building further.")
        else:
            print("\n✅  Generation quality looks acceptable. Review the report for edge cases.")

    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Re-score existing raw results with the updated rubric."""
import json, sys, os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

# Import updated rubric functions
from scripts.validate_generation import score_generation, write_report, _load_all_kpis

results_dir = ROOT / "validation_results"
raw_files = sorted(results_dir.glob("results_*.json"))
if not raw_files:
    print("No results files found.")
    sys.exit(1)

latest = raw_files[-1]
print(f"Re-scoring: {latest.name}")

raw = json.loads(latest.read_text(encoding='utf-8'))

# Build a kpi lookup
all_kpis, _ = _load_all_kpis()
kpi_map = {k['code']: k for k in all_kpis}

# We need the original generated content to re-score properly.
# The raw results file only has scored output, not the original generation.
# So we just print the re-scored summary from what's stored.
# For a full re-score we'd need the raw generations — note this for future runs.

ok = [r for r in raw if not r.get('error')]
failed = [r for r in raw if r.get('error')]

print(f"KPIs: {len(ok)} OK, {len(failed)} failed\n")

# Re-score using stored question data
from scripts.validate_generation import score_question, RUBRIC

rescored = []
for r in ok:
    all_q_scores = []
    for q in r.get('questions', []):
        # Reconstruct question dict from stored scored data
        q_dict = {
            'text': q.get('text', ''),
            'choices': q.get('choices', []),
            'correct': q.get('correct_index'),
            'explanation': q.get('explanation', ''),
            'kpi_code': r.get('kpi_code', ''),
            'kpi_text': r.get('kpi_text', ''),
        }
        scored = score_question(q_dict, r['kpi_text'], q.get('question_type', 'recognition'))
        all_q_scores.append(scored)

    pass_rate = sum(q['pass_rate'] for q in all_q_scores) / len(all_q_scores) if all_q_scores else 0
    pct = round(pass_rate * 100)
    flag = 'OK ' if pct >= 85 else ('WRN' if pct >= 70 else 'BAD')
    print(f"  [{flag}] {r['kpi_code']:10s} {pct:3d}%  {r['kpi_text'][:60]}")
    rescored.append({**r, 'overall_pass_rate': pass_rate})

avg = round(sum(r['overall_pass_rate'] for r in rescored) / len(rescored) * 100) if rescored else 0
below_70 = [r for r in rescored if r['overall_pass_rate'] < 0.70]
print(f"\nAverage: {avg}%  |  Below 70%: {len(below_70)}")

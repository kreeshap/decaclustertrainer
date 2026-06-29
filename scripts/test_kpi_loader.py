#!/usr/bin/env python3
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.learn_helpers import _load_all_kpis, _KPI_CACHE

kpis, events = _load_all_kpis()

print("Events loaded:")
for e in events:
    kpi_count = len([k for k in kpis if k['event'] == e['id']])
    print(f"  {e['name']} ({e['cluster']}) -> {kpi_count} KPIs, tier sample: {set(k['tier'] for k in kpis if k['event'] == e['id'])}")

print()
print(f"Total KPIs: {len(kpis)}")

# Verify tier3 accounting indicators are now loaded
acct_kpis = [k for k in kpis if 'tier 3' in k.get('tier', '').lower() or 'accounting_application' in k.get('event', '')]
print(f"Tier 3 KPIs (Accounting pathway): {len(acct_kpis)}")
if acct_kpis:
    print(f"  Sample: {acct_kpis[0]['code']} - {acct_kpis[0]['text'][:70]}")

# Verify cache is working
kpis2, events2 = _load_all_kpis()
print()
print(f"Cache works (same object): {kpis is kpis2}")

# Verify question_type field in _normalise_db_question
from app.learn_helpers import _normalise_db_question
row = {'id': 'abc', 'question_text': 'Q?', 'choices': [], 'correct_index': 0,
       'explanation': '', 'kpi_code': 'BL:001', 'kpi_text': 'test',
       'kpi_cluster': 'BL', 'deca_cluster': 'Finance', 'event_id': 'fin',
       'question_type': 'application'}
normed = _normalise_db_question(row)
print(f"question_type passed through normalise: {normed.get('question_type')}")

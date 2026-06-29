#!/usr/bin/env python3
"""Audit current state of learn mode against the v1 checklist."""
import sys, os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from app.learn_helpers import _load_all_kpis

kpis, events = _load_all_kpis()
print("=== Events in system ===")
for e in events:
    cnt = len([k for k in kpis if k['event'] == e['id']])
    tiers = set(k['tier'] for k in kpis if k['event'] == e['id'])
    print(f"  {e['id']:<50s} {cnt:>4} KPIs  cluster={e['cluster']}  tiers={tiers}")

print()
print(f"Total KPIs: {len(kpis)}")

# Check what clusters.js lists as events
print()
print("=== CLUSTERS.js events with JSONs ===")
# Read clusters.js
import re
with open(os.path.join(ROOT, 'static/js/clusters.js'), encoding='utf-8') as f:
    js = f.read()

# Find all event names in clusters.js
event_names_in_js = re.findall(r'"([^"]+\.json|[A-Z][^"]{5,})"', js)
# Just get the events array items
events_section = re.search(r'events:\s*\[(.*?)\]', js, re.DOTALL)
if events_section:
    names = re.findall(r'"([^"]+)"', events_section.group(1))
    print("  Finance cluster events in clusters.js:")
    for n in names[:10]:
        matched = any(e['name'] == n for e in events)
        print(f"    {'OK' if matched else 'NO JSON'} {n}")

print()
print("=== Routes audit ===")
with open(os.path.join(ROOT, 'app/routes/learn.py'), encoding='utf-8') as f:
    routes = f.read()
route_list = re.findall(r'@learn_bp\.(get|post)\("([^"]+)"', routes)
for method, path in route_list:
    print(f"  {method.upper():<5} {path}")

print()
print("=== Checklist audit ===")
with open(os.path.join(ROOT, 'static/js/learn.js'), encoding='utf-8') as f:
    js_learn = f.read()
with open(os.path.join(ROOT, 'templates/learn.html'), encoding='utf-8') as f:
    html = f.read()

checks = [
    ("Event selected",                    "ct_selected_event" in js_learn),
    ("Session generated",                 "startSession" in js_learn),
    ("Due KPIs selected (get_due_kpis)",  "get_due_kpis" in routes),
    ("Recognition questions generated",   "recognition_questions" in routes),
    ("Application questions generated",   "application_question" in routes),
    ("Explanations shown",                "explanation-box" in html),
    ("Mastery updated (user_kpi_mastery)","user_kpi_mastery" in routes),
    ("SRS scheduled (user_srs_state)",    "user_srs_state" in routes),
    ("Progress indicators shown",         "m-mastery" in html and "m-streak" in html),
    ("Session summary shown",             "state-summary" in html),
    ("Exam events supported",             "examOnly" in js_learn),
    ("Principles events supported",       "principles" in js_learn),
    ("Analytics collected (DB writes)",   "_upsert_daily_activity" in routes),
    ("Analytics endpoint (/api/learn/analytics)", "/api/learn/analytics" in routes),
    ("Exam-only mode logic (no roleplay)","examOnly" in js_learn and "currentLearnMode" in js_learn),
    ("Principles mode logic",             "principles" in js_learn and "currentLearnMode" in js_learn),
    ("Session summary: recognition acc",  "sum-accuracy" in html),
    ("Session summary: weakest KPIs",     "weak-kpis" in html or "sum-kpi-gains" in html),
    ("Session summary: next review hint", "next_review" in routes),
    ("Event type routing (exam vs roleplay)", "examOnly" in js_learn),
]
for label, result in checks:
    status = "DONE" if result else "MISSING"
    print(f"  [{status}] {label}")

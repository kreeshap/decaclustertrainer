#!/usr/bin/env python3
import os
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def read(rel):
    return open(os.path.join(BASE, rel), encoding='utf-8').read()

js      = read('static/js/learn.js')
html    = read('templates/learn.html')
helpers = read('app/learn_helpers.py')
routes  = read('app/routes/learn.py')
css     = read('static/styles/learn.css')

checks = [
    ('learn_extra.js loaded in learn.html',          'learn_extra.js' in html),
    ('due-summary-count null-safe in renderMastery',  'due-summary-count' in js and 'dueCntEl' in js),
    ('weak KPI shows kpi_text not kpi_code',          'k.kpi_text || k.kpi_code' in js),
    ('active recall continue button',                 'ar-continue-btn' in js),
    ('application question badge in showQuestion',    'q-type-badge' in js),
    ('recognition_questions in generate route',       'recognition_questions' in routes),
    ('application_question in generate route',        'application_question' in routes),
    ('question_type in _normalise_db_question',       'question_type' in helpers),
    ('_KPI_CACHE module-level cache',                 '_KPI_CACHE' in helpers),
    ('tier3 key handling in _load_all_kpis',          "tier3" in helpers),
    ('application badge CSS added',                   'q-type-application' in css),
    ('review-summary-btn wired',                      'review-summary-btn' in js),
    ('startQuestions splits recognition/application', 'availableRecognition' in js),
    ('migration 0008 exists',                         os.path.exists(os.path.join(BASE, 'supabase/migrations/0008_question_type.sql'))),
]

all_ok = True
for label, result in checks:
    status = 'OK  ' if result else 'FAIL'
    if not result:
        all_ok = False
    print(f'  {status}  {label}')

print()
print('All checks passed.' if all_ok else 'Some checks FAILED.')

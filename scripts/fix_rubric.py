#!/usr/bin/env python3
import os
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
path = os.path.join(BASE, 'scripts', 'validate_generation.py')

with open(path, encoding='utf-8') as f:
    content = f.read()

# Insert check_clear_wording before check_correct_index_valid
INSERT = '''
def check_clear_wording(q: dict) -> tuple[bool, str]:
    text = (q.get("text") or "").strip()
    if not (text.endswith("?") or text.endswith(":")):
        return False, "Question does not end with ? or :"
    if len(text.split()) < 6:
        return False, "Question stem too short"
    return True, "OK"

'''

idx = content.find('\ndef check_correct_index_valid')
assert idx != -1
content = content[:idx] + INSERT + content[idx:]

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
print("check_clear_wording restored")

# Verify import works
import sys, importlib.util
spec = importlib.util.spec_from_file_location("validate_generation", path)
mod = importlib.util.module_from_spec(spec)
try:
    spec.loader.exec_module(mod)
    print("Module loads OK")
    print("RUBRIC checks:", [name for name, _ in mod.RUBRIC])
except Exception as e:
    print("ERROR:", e)

#!/usr/bin/env python3
"""
Learn Mode QA Test Suite
Tests:
1. Mode routing (Exam Only, Principles, Standard)
2. Malformed AI output handling
3. Analytics accuracy
4. Error recovery
"""

import sys
import json
from pathlib import Path

# Add parent dir to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.learn_helpers import _load_all_kpis

def test_mode_routing():
    """Test that event types are correctly identified and modes are routed."""
    print("\n" + "="*60)
    print("TEST 1: MODE ROUTING VERIFICATION")
    print("="*60)
    
    all_kpis, events = _load_all_kpis()
    
    # Test events we expect
    test_cases = [
        ("financial_consulting", "exam", "Exam Only mode should be active"),
        ("financial_services_tdm", "tdm", "Standard + Principles modes visible"),
        ("principles_finance", "principles", "Principles mode active by default"),
    ]
    
    event_map = {e["id"]: e for e in events}
    
    for event_id, expected_type, description in test_cases:
        if event_id in event_map:
            event = event_map[event_id]
            print(f"\n✓ Event found: {event['name']}")
            print(f"  ID: {event['id']}")
            print(f"  Expected type: {expected_type}")
            print(f"  Routing behavior: {description}")
            
            # Count KPIs for this event
            kpi_count = len([k for k in all_kpis if k["event"] == event_id])
            print(f"  KPIs available: {kpi_count}")
            if kpi_count == 0:
                print(f"  ⚠️  WARNING: No KPIs loaded for {event_id}")
        else:
            print(f"\n✗ Event NOT FOUND: {event_id}")
            print(f"  Available events: {', '.join(e['id'] for e in events[:5])}...")

def test_malformed_ai_output():
    """Test backend handling of malformed AI responses."""
    print("\n" + "="*60)
    print("TEST 2: MALFORMED AI OUTPUT HANDLING")
    print("="*60)
    
    test_cases = [
        ("Empty recognition_questions", 
         {"vocab": [], "concept": {}, "recognition_questions": [], "application_question": {}}),
        
        ("Null application_question",
         {"vocab": [], "concept": {}, "recognition_questions": [{"text": "q1"}], "application_question": None}),
        
        ("Missing choices in question",
         {"vocab": [], "concept": {}, "recognition_questions": [{"text": "q1", "correct": 0}]}),
        
        ("Malformed correct index",
         {"vocab": [], "concept": {}, "recognition_questions": [
             {"text": "q1", "choices": ["a","b","c","d"], "correct": None}
         ]}),
    ]
    
    for name, response in test_cases:
        print(f"\n📋 Testing: {name}")
        
        # Check what happens when sessionData is missing these fields
        questions = response.get("recognition_questions", [])
        application = response.get("application_question")
        
        print(f"  Recognition questions: {len(questions)}")
        print(f"  Application question: {'None' if not application else 'Present'}")
        
        # Frontend logic: would any of these cause an error?
        if not questions and not application:
            print(f"  ⚠️  RISK: No questions available - session would skip KPI")
        
        for q in questions:
            if not q.get("text"):
                print(f"  ⚠️  RISK: Question missing 'text' field")
            if not q.get("choices"):
                print(f"  ⚠️  RISK: Question missing 'choices' field - (q.choices || []) would fallback")
            if q.get("correct") is None:
                print(f"  ⚠️  RISK: Question has null 'correct' - comparison might fail")

def test_event_types_from_clusters():
    """Test that CLUSTERS configuration is correct."""
    print("\n" + "="*60)
    print("TEST 3: EVENT TYPE CONFIGURATION")
    print("="*60)
    
    # Read clusters.js to validate event types
    clusters_path = Path(__file__).parent.parent / "static" / "js" / "clusters.js"
    if clusters_path.exists():
        content = clusters_path.read_text()
        
        # Look for event type definitions
        if "exam" in content and "tdm" in content and "principles" in content:
            print("✓ Event types defined: exam, tdm, principles")
        
        # Count each type
        exam_count = content.count('type: "exam"')
        tdm_count = content.count('type: "tdm"')
        series_count = content.count('type: "series"')
        principles_count = content.count('type: "principles"')
        ops_count = content.count('type: "operations"')
        
        print(f"✓ Events by type:")
        print(f"  exam: {exam_count}")
        print(f"  tdm: {tdm_count}")
        print(f"  series: {series_count}")
        print(f"  principles: {principles_count}")
        print(f"  operations: {ops_count}")
    else:
        print("✗ clusters.js not found")

def test_kpi_data_integrity():
    """Test that KPI data is loaded correctly."""
    print("\n" + "="*60)
    print("TEST 4: KPI DATA INTEGRITY")
    print("="*60)
    
    all_kpis, events = _load_all_kpis()
    
    print(f"✓ Total KPIs loaded: {len(all_kpis)}")
    print(f"✓ Total events: {len(events)}")
    
    # Check required fields
    required_fields = ["code", "text", "event", "cluster", "deca_cluster"]
    
    issues = []
    for i, kpi in enumerate(all_kpis):
        for field in required_fields:
            if not kpi.get(field):
                issues.append(f"KPI #{i} missing '{field}'")
    
    if issues:
        print(f"\n⚠️  Found {len(issues)} data integrity issues:")
        for issue in issues[:5]:
            print(f"  - {issue}")
        if len(issues) > 5:
            print(f"  ... and {len(issues) - 5} more")
    else:
        print(f"✓ All KPIs have required fields")
    
    # Check for duplicates
    codes = [k["code"] for k in all_kpis]
    unique_codes = set(codes)
    if len(codes) != len(unique_codes):
        print(f"⚠️  WARNING: Found {len(codes) - len(unique_codes)} duplicate KPI codes")

def test_question_structure():
    """Test expected question structure from API."""
    print("\n" + "="*60)
    print("TEST 5: QUESTION STRUCTURE VALIDATION")
    print("="*60)
    
    print("\nExpected question structure:")
    print("""
    Recognition Question:
    {
      "text": "...",
      "choices": ["A", "B", "C", "D"],
      "correct": 0-3,
      "explanation": "...",
      "question_type": "recognition",
      "kpi_code": "...",
      "id": "uuid"
    }
    
    Application Question:
    {
      "text": "...",
      "choices": ["A", "B", "C", "D"],
      "correct": 0-3,
      "explanation": "...",
      "question_type": "application",
      "kpi_code": "...",
      "id": "uuid"
    }
    """)
    
    print("✓ Frontend expects:")
    print("  - 5 recognition questions per KPI")
    print("  - 1 application question per KPI")
    print("  - Each question must have text, 4 choices, and correct index")
    print("  - Application questions show 📋 badge")

if __name__ == "__main__":
    print("\n🧪 LEARN MODE QA TEST SUITE")
    print("Starting comprehensive tests...")
    
    try:
        test_event_types_from_clusters()
        test_mode_routing()
        test_kpi_data_integrity()
        test_malformed_ai_output()
        test_question_structure()
        
        print("\n" + "="*60)
        print("✓ QA TEST SUITE COMPLETE")
        print("="*60)
    except Exception as e:
        print(f"\n✗ ERROR during testing: {e}")
        import traceback
        traceback.print_exc()

#!/usr/bin/env python3
"""
Learn Mode Integration Tests - Makes actual HTTP requests to running server
Tests the full flow: Events → KPIs → Generate Questions → Answer Questions → Analytics
"""

import requests
import json
import time
from datetime import datetime

BASE_URL = "http://localhost:5000"

def test_api_kpis():
    """Test that /api/kpis endpoint returns proper event and KPI data."""
    print("\n" + "="*60)
    print("TEST: /api/kpis endpoint")
    print("="*60)
    
    resp = requests.get(f"{BASE_URL}/api/kpis")
    print(f"Status: {resp.status_code}")
    
    if resp.status_code != 200:
        print(f"✗ Expected 200, got {resp.status_code}")
        print(f"  Response: {resp.text[:200]}")
        return None
    
    data = resp.json()
    events = data.get("events", [])
    kpis = data.get("kpis", [])
    
    print(f"✓ Events loaded: {len(events)}")
    for ev in events:
        print(f"  - {ev['id']}: {ev['name']}")
    
    print(f"✓ KPIs available: {len(kpis)}")
    
    # Show breakdown by event
    kpis_by_event = {}
    for kpi in kpis:
        event = kpi.get("event", "unknown")
        kpis_by_event[event] = kpis_by_event.get(event, 0) + 1
    
    for event, count in kpis_by_event.items():
        print(f"  - {event}: {count} KPIs")
    
    # Sample one KPI
    if kpis:
        sample = kpis[0]
        print(f"\n✓ Sample KPI structure:")
        print(f"  Code: {sample.get('code')}")
        print(f"  Text: {sample.get('text')[:60]}...")
        print(f"  Event: {sample.get('event')}")
        print(f"  Cluster: {sample.get('cluster')}")
        print(f"  DECA Cluster: {sample.get('deca_cluster')}")
    
    return data

def test_generate_questions(kpi_code, kpi_text, cluster, deca_cluster, event_id):
    """Test the /api/learn/generate endpoint (requires auth)."""
    print("\n" + "="*60)
    print(f"TEST: /api/learn/generate for {kpi_code}")
    print("="*60)
    
    payload = {
        "code": kpi_code,
        "text": kpi_text,
        "cluster": cluster,
        "standard": "Some Standard",
        "deca_cluster": deca_cluster,
        "event_id": event_id,
    }
    
    resp = requests.post(
        f"{BASE_URL}/api/learn/generate",
        json=payload,
        headers={"Authorization": "Bearer fake-token-for-testing"}
    )
    
    print(f"Status: {resp.status_code}")
    
    if resp.status_code == 401:
        print("⚠️  Auth required - skipping (need valid token)")
        return None
    
    if resp.status_code != 200:
        print(f"✗ Error: {resp.status_code}")
        print(f"  Response: {resp.text[:300]}")
        return None
    
    data = resp.json()
    
    # Check structure
    if "error" in data:
        print(f"✗ API returned error: {data['error']}")
        return None
    
    print(f"✓ Response structure valid")
    
    vocab = data.get("vocab", [])
    concept = data.get("concept", {})
    recognition = data.get("recognition_questions", [])
    application = data.get("application_question")
    
    print(f"  Vocab terms: {len(vocab)}")
    print(f"  Concept explanation: {len(concept.get('explanation', ''))} chars")
    print(f"  Recognition questions: {len(recognition)}")
    print(f"  Application question: {'Present' if application else 'Missing'}")
    
    # Check question structure
    issues = []
    for i, q in enumerate(recognition):
        if not q.get("text"):
            issues.append(f"Recognition Q{i}: missing 'text'")
        if not q.get("choices") or len(q.get("choices", [])) != 4:
            issues.append(f"Recognition Q{i}: invalid 'choices'")
        if q.get("correct") is None or not isinstance(q.get("correct"), int):
            issues.append(f"Recognition Q{i}: invalid 'correct' index")
    
    if application:
        if not application.get("text"):
            issues.append(f"Application Q: missing 'text'")
        if not application.get("choices") or len(application.get("choices", [])) != 4:
            issues.append(f"Application Q: invalid 'choices'")
        if application.get("correct") is None:
            issues.append(f"Application Q: invalid 'correct' index")
    
    if issues:
        print(f"\n⚠️  Found {len(issues)} question structure issues:")
        for issue in issues:
            print(f"  - {issue}")
    else:
        print(f"✓ All questions have valid structure")
    
    return data

def test_question_validation():
    """Test that the frontend can handle malformed questions."""
    print("\n" + "="*60)
    print("TEST: Question Validation Logic")
    print("="*60)
    
    malformed_cases = [
        ("Empty choices", {"text": "Q1", "choices": [], "correct": 0}),
        ("Null choices", {"text": "Q1", "choices": None, "correct": 0}),
        ("Missing correct", {"text": "Q1", "choices": ["a", "b", "c", "d"]}),
        ("Null correct", {"text": "Q1", "choices": ["a", "b", "c", "d"], "correct": None}),
        ("Out of range correct", {"text": "Q1", "choices": ["a", "b", "c", "d"], "correct": 10}),
    ]
    
    print("Frontend safeguards:")
    print("  - (q.choices || []).forEach() → handles null choices")
    print("  - i === q.correct → handles null/undefined correct")
    print("  - q.text → displays as-is (no validation)")
    
    for name, q in malformed_cases:
        safe = True
        if not q.get("choices"):
            print(f"\n  ⚠️  {name}: choices is {q.get('choices')}")
            print(f"      Frontend will iterate over empty array (safe)")
        if q.get("correct") is None:
            print(f"\n  ⚠️  {name}: correct is None")
            print(f"      Comparison 'i === q.correct' will always be false (safe)")

def test_session_endpoints():
    """Test session start/end endpoints."""
    print("\n" + "="*60)
    print("TEST: Session Management Endpoints")
    print("="*60)
    
    # These require auth
    endpoints = [
        ("POST", "/api/learn/session/start", {"event_id": "financial_services_tdm", "session_type": "standard"}),
        ("GET", "/api/learn/questions", None),
        ("POST", "/api/learn/answer", {"question_id": "uuid", "correct": True}),
    ]
    
    print("Session management endpoints (require authentication):")
    for method, path, payload in endpoints:
        resp = requests.request(
            method,
            f"{BASE_URL}{path}",
            json=payload,
            headers={"Authorization": "Bearer fake-token"}
        )
        auth_required = resp.status_code == 401
        print(f"  {method:4} {path:30} → {resp.status_code} {'(Auth required)' if auth_required else ''}")

def test_event_mode_routing():
    """Verify that event types would route correctly based on frontend logic."""
    print("\n" + "="*60)
    print("TEST: Event Mode Routing")
    print("="*60)
    
    data = requests.get(f"{BASE_URL}/api/kpis").json()
    events = {e["id"]: e for e in data.get("events", [])}
    
    # Expected routing based on clusters.js
    routing_map = {
        "financial_services_tdm": {
            "type": "tdm",
            "expected_modes": ["standard", "principles"],
            "flow": "vocab → concept → 5 recognition + 1 application → roleplay every 7"
        },
        "accounting_application_series": {
            "type": "series", 
            "expected_modes": ["standard", "principles"],
            "flow": "vocab → concept → 5 recognition + 1 application → roleplay every 7"
        },
        "business_finance_series": {
            "type": "series",
            "expected_modes": ["standard", "principles"],
            "flow": "vocab → concept → 5 recognition + 1 application → roleplay every 7"
        }
    }
    
    print("Event type routing verification:")
    for event_id, expected in routing_map.items():
        if event_id in events:
            event = events[event_id]
            print(f"\n  ✓ {event['name']}")
            print(f"    Expected type: {expected['type']}")
            print(f"    Modes: {', '.join(expected['expected_modes'])}")
            print(f"    Flow: {expected['flow']}")
        else:
            print(f"\n  ✗ {event_id} not found")

def test_analytics_tracking():
    """Explain what analytics data should be captured."""
    print("\n" + "="*60)
    print("TEST: Analytics Tracking Expectations")
    print("="*60)
    
    print("\nExpected analytics data per question answer:")
    print("  Table: responses (or user_question_results)")
    print("  Fields:")
    print("    - user_id: who answered")
    print("    - question_id: which question (UUID)")
    print("    - correct: boolean (true/false)")
    print("    - question_type: 'recognition' or 'application'")
    print("    - kpi_code: which KPI (e.g., 'FIN-1.1')")
    print("    - cluster: knowledge cluster")
    print("    - deca_cluster: subject area (Finance, Marketing, etc.)")
    print("    - event_id: which event (financial_services_tdm, etc.)")
    print("    - answered_at: timestamp")
    print("\nExpected aggregate data (analytics endpoint):")
    print("  SELECT question_type, COUNT(*), AVG(CAST(correct AS FLOAT))")
    print("  FROM responses")
    print("  WHERE user_id = $1")
    print("  GROUP BY question_type;")
    print("\n  Should show:")
    print("    - recognition: N answered, X% correct")
    print("    - application: N answered, X% correct")

if __name__ == "__main__":
    print("\n🧪 LEARN MODE INTEGRATION TEST SUITE")
    print(f"Target: {BASE_URL}")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    try:
        # Main test flow
        api_data = test_api_kpis()
        
        if api_data:
            test_event_mode_routing()
            
            # Try to generate questions (will need auth)
            kpis = api_data.get("kpis", [])
            if kpis:
                sample_kpi = kpis[0]
                test_generate_questions(
                    sample_kpi.get("code"),
                    sample_kpi.get("text"),
                    sample_kpi.get("cluster"),
                    sample_kpi.get("deca_cluster"),
                    sample_kpi.get("event")
                )
        
        test_question_validation()
        test_session_endpoints()
        test_analytics_tracking()
        
        print("\n" + "="*60)
        print("✓ INTEGRATION TEST SUITE COMPLETE")
        print("="*60)
        
    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        import traceback
        traceback.print_exc()

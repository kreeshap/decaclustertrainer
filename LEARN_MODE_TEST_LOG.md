# Learn Mode Test Log

**Purpose**: Evidence of what was actually tested — not memory, not assumption. This log is your proof 6 months from now.

**Date**: _______________  
**Tester**: _______________  
**Test User Email**: _______________  
**Browser**: _______________  
**Time Started**: _______________

---

## Ground Rules

You don't need:
- Automated QA frameworks
- Integration test suites
- Elaborate validation systems

You need: one person, one test account, a couple hours, and brutal honesty about what breaks.

---

## Test 1: Session Completion

*Can a student start and finish a session without it breaking?*

**Setup**: Login → Select Accounting Application Series → Complete 3 KPIs manually

| Test | Expected | Actual | Pass? | Notes |
|------|----------|--------|-------|-------|
| Login | Login succeeds, redirected to dashboard | | ✅/❌ | |
| Event select | Accounting Series is available and selectable | | ✅/❌ | |
| Session start | Session loads, first KPI appears | | ✅/❌ | |
| KPI 1 — Vocab | Vocab cards appear and are readable | | ✅/❌ | |
| KPI 1 — Concept | Concept explanation appears | | ✅/❌ | |
| KPI 1 — Questions | 5 recognition + 1 application question appear | | ✅/❌ | Count: ___ |
| KPI 2 — Loads | KPI 2 loads cleanly after completing KPI 1 | | ✅/❌ | |
| KPI 3 — Loads | KPI 3 loads cleanly | | ✅/❌ | |
| Session summary | Summary screen appears after KPI 3 | | ✅/❌ | |
| Summary numbers | Numbers visible (Q answered, correct, accuracy %) | | ✅/❌ | |
| Console clean | No red errors in browser console | | ✅/❌ | Errors: ___ |
| **VERDICT** | **All rows pass** | | **✅/❌** | |

---

## Test 2: SRS Scheduling

*Does the spaced repetition algorithm actually update the schedule?*

**Setup**: Answer questions on 1 KPI wrong, then correct. Query the database both times.

**KPI Code Tested**: _____________

| Test | Expected | Actual | Pass? | Notes |
|------|----------|--------|-------|-------|
| Wrong answer → interval | interval_days = 0 or 1 | | ✅/❌ | Actual value: ___ |
| Wrong answer → ease factor | ease_factor drops below 2.5 | | ✅/❌ | Actual value: ___ |
| Correct answer → interval | interval_days increases from previous | | ✅/❌ | Before: ___ After: ___ |
| Correct answer → ease factor | ease_factor ≥ 2.0 | | ✅/❌ | Actual value: ___ |
| next_review date | next_review is in the future | | ✅/❌ | Date shown: ___ |
| **VERDICT** | **All rows pass** | | **✅/❌** | |

**DB Query Used**:
```sql
SELECT kpi_code, ease_factor, interval_days, next_review, repetitions
FROM user_srs_state
WHERE user_id = '___'
ORDER BY last_reviewed DESC LIMIT 5;
```
**Raw Result**:
```
(paste here)
```

---

## Test 3: Analytics Accuracy

*Do the numbers in the database match what actually happened?*

**Setup**: Answer exactly — 2 recognition (1 correct, 1 wrong), 1 application (wrong). Then verify the database.

| Test | Expected | Actual | Pass? | Notes |
|------|----------|--------|-------|-------|
| Recognition rows recorded | 2 rows with question_type = "recognition" | | ✅/❌ | |
| Recognition correct count | 1 correct out of 2 | | ✅/❌ | |
| Recognition accuracy | 50% | | ✅/❌ | Actual: ___% |
| Application rows recorded | 1 row with question_type = "application" | | ✅/❌ | |
| Application correct count | 0 correct out of 1 | | ✅/❌ | |
| Application accuracy | 0% | | ✅/❌ | Actual: ___% |
| Dashboard shows matching numbers | Dashboard accuracy matches DB query | | ✅/❌ | |
| **VERDICT** | **All rows pass** | | **✅/❌** | |

**DB Query Used**:
```sql
SELECT question_type, COUNT(*) as total, SUM(CAST(correct AS INT)) as correct_count
FROM responses
WHERE user_id = '___'
GROUP BY question_type;
```
**Raw Result**:
```
(paste here)
```

---

## Test 4: Event Routing

*Does each event type send the user down the right flow?*

**Setup**: Start a session for each event type and verify the phases shown.

| Event | Flow Observed | Questions Seen | Roleplay Triggered? | Pass? | Notes |
|-------|--------------|----------------|---------------------|-------|-------|
| Accounting Application Series | Vocab → Concept → Questions → Summary | ___ recog + ___ app | N/A | ✅/❌ | |
| Financial Services TDM | Vocab → Concept → Questions → (Roleplay @ 7 KPIs) | ___ recog + ___ app | YES / NO / Not tested | ✅/❌ | |
| Business Finance Series | Vocab → Concept → Questions → Summary | ___ recog + ___ app | N/A | ✅/❌ | |
| **VERDICT** | **Flows matched expected** | | | **✅/❌** | |

---

## Test 5: Error Recovery

*Does the app handle an AI failure gracefully?*

**Setup**: Simulate or wait for an AI generation failure. Observe what the user sees.

| Test | Expected | Actual | Pass? | Notes |
|------|----------|--------|-------|-------|
| AI failure detected | Error message appears (not a blank screen) | | ✅/❌ | Message text: ___ |
| Retry available | Retry button or option present | | ✅/❌ | |
| Session survives | Can continue or skip without losing session | | ✅/❌ | |
| No data corruption | Previous answers still recorded correctly | | ✅/❌ | |
| **VERDICT** | **All rows pass** | | **✅/❌** | |

---

## Test 6: Ugly Path (Browser Refresh Mid-Session)

*Students do this constantly. Does the session survive?*

**Setup**: Start a session, answer KPI 1 fully, get partway through KPI 2, then hit Ctrl+R.

### Steps Run

```
1. Start session — Event: Accounting Application Series
2. Complete all questions for KPI 1
3. Load KPI 2, answer 3 out of 6 questions
4. REFRESH BROWSER (Ctrl+R)
5. Navigate back to Learn Mode
6. Observe what happens
```

| Test | Expected | Actual | Pass? | Notes |
|------|----------|--------|-------|-------|
| KPI 1 answers preserved | Responses for KPI 1 still in database | | ✅/❌ | |
| Session state on return | Resumes, restarts gracefully, or explains what happened | | ✅/❌ | What happened: ___ |
| No data corruption | No duplicate responses, no null values | | ✅/❌ | |
| User can continue | Can get back to learning without manual intervention | | ✅/❌ | |
| **VERDICT** | **Progress survives, nothing corrupts** | | **✅/❌** | |

**DB Check After Refresh**:
```sql
-- Check for duplicates
SELECT question_id, COUNT(*) FROM responses
WHERE user_id = '___' GROUP BY question_id HAVING COUNT(*) > 1;

-- Check KPI 1 responses still exist
SELECT * FROM responses WHERE user_id = '___' ORDER BY created_at DESC LIMIT 10;
```
**Raw Result**:
```
(paste here)
```

---

## The Five Questions That Matter

Answer these after all tests are done. If all five are YES, Learn Mode v1 is complete.

| Question | Answer | Evidence (which test) |
|----------|--------|-----------------------|
| Can a student finish a session? | YES / NO | Test 1 |
| Does mastery update correctly? | YES / NO | Test 2 |
| Does SRS schedule correctly? | YES / NO | Test 2 |
| Do analytics match reality? | YES / NO | Test 3 |
| Do event types route correctly? | YES / NO | Test 4 |

---

## Issues Found

### Blockers (must fix before declaring v1 complete)
```
1. 
2. 
3. 
```

### Non-blockers (nice to fix, not urgent)
```
1. 
2. 
3. 
```

---

## Final Decision

- [ ] **PASS** — All 5 questions answered YES. Learn Mode v1.0 is complete. Stop adding features.
- [ ] **CONDITIONAL** — 4/5 YES. Fix specific item: _____________. Retest that one thing.
- [ ] **FAIL** — Multiple issues. Document what breaks, fix only that, retest.

---

## Sign-Off

Tested by: _____________________  
Date: _____________________  
Time spent: _____________________  
Ready to call v1 complete: YES / NO / NOT YET

---

*This log exists so you have evidence, not memory. Paste real query results. Write what actually appeared on screen. Future-you will thank present-you for it.*

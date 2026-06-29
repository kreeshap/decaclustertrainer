# Learn Mode Real-World Test - Actual User Flow

**Goal**: Prove Learn Mode works end-to-end with real user

**Time**: 1-2 hours per test session

**Prerequisite**: Throwaway test account (not just code review)

---

## Test 1: Session Completion Flow

### Setup
```
1. Create fresh test account at http://localhost:5000
2. Login with that account
3. Note the user_id from browser console or database
```

### Execution
```
1. Click "Learning"
2. Select "Accounting Application Series" 
3. Click "Start Learning"
4. Complete exactly 3 KPIs:
   - KPI 1: Answer all 6 questions
   - KPI 2: Answer all 6 questions
   - KPI 3: Answer all 6 questions
5. Click "Done" / end session
6. Record session summary numbers
```

### Verification Checklist
```
□ Login succeeds
□ Learning page loads
□ Event selection works
□ Session starts without errors
□ KPI 1: 5 vocab cards appear
□ KPI 1: Concept section displays
□ KPI 1: 5 recognition questions appear
□ KPI 1: 1 application question appears (with badge)
□ KPI 1: Session metrics update (1/6, 2/6, etc.)
□ KPI 2: Loads without error
□ KPI 3: Loads without error
□ Session summary displays
□ Summary shows: total answered, correct count
□ Browser console has NO errors
□ Session summary format looks correct
```

### Pass Criteria
- All questions display
- All explanations display
- Session completes without crashes
- No console errors
- Summary appears

### If It Fails
```
Check browser console for errors:
1. What error message appears?
2. Which KPI fails?
3. Does session recover or crash?

Check network tab:
1. Which API call failed?
2. What HTTP status?
3. Error response message?
```

---

## Test 2: SRS State Verification

### Setup
```
Test user ID: (record from Test 1)
Test user email: (record from Test 1)
Database access: (Supabase SQL editor)
```

### Part A: First Completion (Wrong Answer → Correct Answer)

**Session 1**:
```
1. Start new session with same test user
2. Pick any KPI you haven't studied
3. Get a recognition question WRONG (intentionally pick wrong answer)
4. Get the application question WRONG
5. Note which KPI code (e.g., "BL:153")
6. End session
7. Check SRS state in database (see query below)
```

**Database Check After Session 1**:
```sql
SELECT 
  question_id,
  kpi_code,
  ease_factor,
  interval_days,
  repetitions,
  next_review,
  correct_attempts,
  total_attempts
FROM user_srs_state
WHERE user_id = 'YOUR_USER_ID'
ORDER BY last_reviewed DESC
LIMIT 2;
```

**Expected Results After Wrong Answers**:
```
- interval_days should be 0 or 1
- ease_factor should be < 2.0
- repetitions should be 1
- next_review should be soon (today or tomorrow)
- correct_attempts should be 0
- total_attempts should be 1
```

**Session 2 (Next day or wait a few minutes)**:
```
1. Start new session
2. Get the SAME KPI
3. Get that recognition question CORRECT
4. Get the application question CORRECT
5. End session
```

**Database Check After Session 2**:
```sql
SELECT 
  question_id,
  ease_factor,
  interval_days,
  repetitions,
  next_review,
  correct_attempts,
  total_attempts
FROM user_srs_state
WHERE user_id = 'YOUR_USER_ID'
AND kpi_code = 'BL:153'
ORDER BY last_reviewed DESC
LIMIT 2;
```

**Expected Results After Correct Answers**:
```
- ease_factor should increase (now > 2.0, ideally ~2.3)
- interval_days should INCREASE from previous (now 1, 3, or more)
- repetitions should be 2
- next_review should be further in future
- correct_attempts should be 2
- total_attempts should be 2
```

### Pass Criteria
✅ SRS state created after first answer  
✅ Interval increases after correct answer  
✅ Ease factor adjusts based on performance  
✅ Next review date moves forward  

### If It Fails
```
Possible issues:
1. SRS state not being created → Check /api/learn/answer endpoint
2. Interval not changing → SM-2 algorithm might be wrong
3. Next_review staying the same → Date calculation issue
4. Ease factor wrong → Quality scoring issue

Check logs:
1. Is /api/learn/answer being called?
2. Is the response successful (200)?
3. Are the calculations happening server-side?
```

---

## Test 3: Analytics Accuracy

### Setup
```
Test user ID: (from Test 1)
Session: Use a new session
Target: Answer exactly 2 recognition + 1 application
```

### Execution
```
1. Start new session
2. Find a KPI you haven't mastered
3. Answer first 2 recognition questions:
   - Question 1: GET CORRECT
   - Question 2: GET INCORRECT
4. Answer application question:
   - Question 1: GET INCORRECT
5. End session immediately after these 3 questions
```

### Database Check
```sql
SELECT 
  question_type,
  COUNT(*) as count,
  SUM(CAST(correct AS INT)) as correct_count,
  ROUND(100.0 * SUM(CAST(correct AS INT)) / COUNT(*), 1) as accuracy_pct
FROM responses
WHERE user_id = 'YOUR_USER_ID'
AND answered_at > NOW() - INTERVAL 5 MINUTES
GROUP BY question_type
ORDER BY question_type;
```

**Expected Results**:
```
question_type    count    correct_count    accuracy_pct
recognition      2        1                50.0
application      1        0                0.0
```

### Pass Criteria
✅ Recognition questions recorded as "recognition"  
✅ Application questions recorded as "application"  
✅ Correct count matches answers
✅ Accuracy % calculates correctly: (1/2)*100 = 50%, (0/1)*100 = 0%  

### If It Fails
```
Likely issues:
1. Wrong question_type value → Check /api/learn/answer code
2. Wrong correct values → Check answer submission logic
3. Missing records → Check database connection

Verify:
1. Are responses being written to DB?
2. Is question_type being set?
3. Is correct boolean being stored?
```

---

## Test 4: Event Routing Behavior

### Setup
```
Three different events to test:
1. Accounting Application Series
2. Business Finance Series
3. Financial Services Team Decision Making
```

### Test Each Event
```
For each event:
1. Select event
2. Click "Start Learning"
3. Observe which modes are available
4. Observe which flow appears
```

### Expected Behavior
```
Accounting Application Series (type: series):
  - Modes: Standard, Principles, Active Recall visible
  - Flow: Vocab → Concept → 5 recognition + 1 application
  - Roleplay: Every 7 KPIs (if you go that far)

Business Finance Series (type: series):
  - Modes: Standard, Principles, Active Recall visible
  - Flow: Vocab → Concept → 5 recognition + 1 application
  - Roleplay: Every 7 KPIs

Financial Services Team Decision Making (type: tdm):
  - Modes: Standard, Principles, Active Recall visible
  - Flow: Vocab → Concept → 5 recognition + 1 application
  - Roleplay: Every 7 KPIs
```

### Verification Checklist
```
For each event:
  □ Event loads without error
  □ Mode buttons visible
  □ Start Learning button works
  □ Vocab phase appears
  □ Concept phase appears
  □ Questions phase has 5 recognition + 1 application
  □ Progress bar shows KPI count
  □ No console errors
```

### Pass Criteria
✅ All three events start sessions  
✅ Flows are consistent (vocab → concept → questions)  
✅ All questions appear  
✅ No crashes or errors  

---

## Test 5: Error Recovery

### Test AI Failure Handling

**Scenario**: What if Groq/Gemini API times out?

```
1. Start session on a KPI
2. Watch as it loads ("Generating questions...")
3. Simulate timeout (let it hang for 30+ seconds)
4. Observe what happens
```

### Expected Behavior
```
Option A: Error message appears + Retry button
Option B: Automatically retries once
Option C: Shows cached version if available
```

### Verification
```
□ Error message displays (if applicable)
□ Retry button works (if applicable)
□ User can continue or move to next KPI
□ Session doesn't crash
□ Browser console has no JavaScript errors
```

### If It Fails
```
What happens instead?
1. Does page hang forever?
2. Does page crash?
3. Is there an unclear error message?

This tells you how robust error handling is.
```

---

## Test Results Template

### Session 1: Completion Flow
```
Date/Time: _____________________
Test User: _____________________
Event Selected: Accounting Application Series
KPIs Completed: 3 / 3 ✓

Results:
  Total Questions Answered: _____
  Total Correct: _____
  Recognition Accuracy: ____% (should be ~70-80%)
  Application Accuracy: ____% (should be ~50-70%)
  
Errors Observed: _____________________
Pass/Fail: _____
```

### Session 2: SRS Verification
```
Date/Time: _____________________
Test KPI: _________________ (code)

After Wrong Answer:
  interval_days: _____ (expect 0-1)
  ease_factor: _____ (expect < 2.0)
  
After Correct Answer:
  interval_days: _____ (expect > previous)
  ease_factor: _____ (expect > 2.0)

Pass/Fail: _____
```

### Session 3: Analytics Accuracy
```
Date/Time: _____________________

Recognition Questions: 2 answered, 1 correct
  Database shows: 2 answered, 1 correct ✓ / ✗
  Calculated accuracy: 50% ✓ / ✗

Application Questions: 1 answered, 0 correct
  Database shows: 1 answered, 0 correct ✓ / ✗
  Calculated accuracy: 0% ✓ / ✗

Pass/Fail: _____
```

### Session 4: Event Routing
```
Accounting Application Series:
  Mode selection works: ✓ / ✗
  Flow correct: ✓ / ✗
  No errors: ✓ / ✗

Business Finance Series:
  Mode selection works: ✓ / ✗
  Flow correct: ✓ / ✗
  No errors: ✓ / ✗

Financial Services TDM:
  Mode selection works: ✓ / ✗
  Flow correct: ✓ / ✗
  No errors: ✓ / ✗

Pass/Fail: _____
```

---

## Pass/Fail Decision

### PASS (Proceed to Beta)
✅ All 4 test sessions complete  
✅ No unexpected errors  
✅ Analytics numbers accurate  
✅ SRS calculations make sense  
✅ All events route correctly  

### FAIL (Identify & Fix)
❌ Session crashes mid-way  
❌ Analytics numbers wrong  
❌ SRS not updating  
❌ Event routing broken  
❌ Unexpected console errors  

### PARTIAL (Fix & Retest)
⚠️ 3/4 tests pass  
⚠️ Minor errors observed  
⚠️ Some analytics off  

---

## What Happens After These Tests Pass

Learn Mode v1.0 is PROVEN COMPLETE.

**Action**: Freeze Learn Mode for new features. Move to:
- Bug fixes only (if issues found)
- Monitoring/observability
- User documentation
- Performance optimization
- Deployment to production

**NOT**: Confidence tracking, reflection, mastery modes, etc.

---

## Running This Test

**Time Investment**: ~2 hours total  
**Outcome**: Know for certain if Learn Mode works or what's broken  
**Value**: Orders of magnitude higher than more code review  

This is where real learning happens about what actually works vs. what looks like it works.


# Learn Mode QA Punch List

## Status: FEATURE-COMPLETE - Ready for QA Phase

**Last Updated**: June 8, 2026  
**Next Action**: Complete manual testing with authenticated user

---

## Critical Path Testing

### □ Exam Only flow works
- **What**: Financial Consulting (or other exam event) should:
  - Skip vocab/concept phases
  - Show recognition questions only
  - Hide application questions
  - Not show roleplay prompt
- **How to test**: 
  1. Sign in
  2. Select exam-type event (need Principles event data for full test)
  3. Verify only questions phase shows
- **Pass Criteria**: 5-6 recognition questions, 0 application, no roleplay

---

### □ Principles flow works
- **What**: Principles of Finance (or similar) should:
  - Show vocab cards
  - Show concept explanation
  - Show ONLY 1 application question
  - NOT show recognition questions
  - NOT show roleplay
- **How to test**:
  1. Sign in
  2. Select Principles event
  3. Verify flow
- **Pass Criteria**: vocab → concept → 1 application question only

---

### □ Team Decision flow works
- **What**: Financial Services Team Decision Making should:
  - Show vocab phase
  - Show concept phase
  - Show 5 recognition + 1 application questions
  - Show mini roleplay every 7 KPIs
- **How to test**:
  1. Sign in
  2. Select Financial Services TDM event
  3. Complete 7 KPIs to trigger roleplay
- **Pass Criteria**: Roleplay prompt appears after 7th KPI

---

### □ Session summary accurate
- **What**: After completing session, summary should show:
  - Total questions answered
  - Total correct answers
  - Recognition accuracy % (count/answered * 100)
  - Application accuracy % (count/answered * 100)
  - KPIs completed count
  - Time spent
- **How to test**:
  1. Complete a session manually counting answers
  2. Compare with session summary
  3. Verify math is correct
- **Pass Criteria**: All numbers match manual count within ±0 (exact match required)

---

### □ SRS updates correctly
- **What**: After answering questions:
  - user_srs_state table should have entries
  - ease_factor should be between 1.3 and 2.5
  - interval_days should increase for correct answers
  - next_review date should be in future
  - repetitions count should increment
- **How to test**:
  1. Answer 5 recognition questions (mix of correct/incorrect)
  2. Query: `SELECT * FROM user_srs_state WHERE user_id = 'your_id' LIMIT 5`
  3. Verify values
- **Pass Criteria**: 
  - Correct answers: interval_days > 0, ease_factor >= 2.0
  - Incorrect answers: interval_days = 0 or 1, ease_factor < 2.0

---

### □ Analytics accurate
- **What**: Responses should be recorded with:
  - question_type: "recognition" or "application" (NOT mixed)
  - Event metadata preserved
  - Cluster data preserved
  - DECA cluster saved
- **How to test**:
  1. Answer 5 recognition + 1 application question
  2. Query: `SELECT question_type, COUNT(*), AVG(CAST(correct AS FLOAT)) FROM responses GROUP BY question_type`
  3. Verify counts: 5 recognition, 1 application
- **Pass Criteria**:
  - recognition: 5 responses, question_type="recognition"
  - application: 1 response, question_type="application"

---

### □ Empty KPI handling
- **What**: If KPI has no questions, should:
  - Not crash
  - Skip to next KPI
  - Show graceful message (or just advance)
- **How to test**:
  1. (Requires injecting malformed KPI into session queue)
  2. Or: Intentionally clear vocabList in developer console
  3. Verify session continues
- **Pass Criteria**: Session doesn't crash, user can continue

---

### □ AI failure handling
- **What**: If Groq/Gemini API fails, should:
  - Show error message
  - Provide "Retry" button
  - Not crash the session
  - Allow user to skip to next KPI or try again
- **How to test**:
  1. Test with invalid API key (simulate failure)
  2. Or: Wait for actual API timeout
  3. Verify error handling
- **Pass Criteria**: Error message displays, retry works, session recovers

---

### □ Mobile layout
- **What**: On mobile (375px width):
  - Vocab cards readable
  - Question text readable
  - 4 choices properly stacked
  - Session summary legible
  - No horizontal scrolling
- **How to test**:
  1. Open browser dev tools
  2. Toggle device toolbar (375px iPhone SE)
  3. Complete a full session on mobile
  4. Check all screens
- **Pass Criteria**: All elements fit, no scrolling, no broken layout

---

## Optional but Recommended

### □ Confidence tracking (Future)
- Currently NOT implemented - deferred
- Would show how confident user was in answer

### □ Reflection tracking (Future)
- Currently NOT implemented - deferred  
- Would prompt for self-reflection after wrong answers

### □ Knowledge graphs (Future)
- Currently NOT implemented - deferred
- Would show relationships between KPIs

---

## Testing Tools

### Browser Console Tests
```javascript
// Check sessionData structure
console.log(sessionData);

// Verify vocab list loaded
console.log(vocabList);

// Check question structure
console.log(qShown);

// Monitor session metrics
console.log({
  sessionQAnswered,
  sessionQCorrect,
  sessionRecogAnswered,
  sessionRecogCorrect,
  sessionAppAnswered,
  sessionAppCorrect
});
```

### Database Queries
```sql
-- Check responses
SELECT COUNT(*), question_type, AVG(CAST(correct AS FLOAT))
FROM responses
WHERE user_id = 'your_user_id'
GROUP BY question_type;

-- Check SRS state
SELECT COUNT(*), AVG(ease_factor), MIN(interval_days), MAX(interval_days)
FROM user_srs_state
WHERE user_id = 'your_user_id';

-- Check mastery updates
SELECT kpi_code, mastery_score
FROM kpi_mastery
WHERE user_id = 'your_user_id'
ORDER BY updated_at DESC
LIMIT 10;

-- Check for duplicate responses
SELECT question_id, COUNT(*)
FROM responses
WHERE user_id = 'your_user_id'
GROUP BY question_id
HAVING COUNT(*) > 1;
```

---

## Environment Setup

### Required for Testing
1. **Database Access**: Need direct Supabase access to verify analytics
2. **User Account**: Need authenticated test user
3. **Browser DevTools**: For console logging and network inspection
4. **API Key Monitor**: Watch for AI generation failures

### Test Data Needed
- At least 3 different events available
- Each event with 5+ KPIs
- Valid Groq/Gemini API keys

---

## Known Limitations

### Current Scope
- ✅ Recognition questions working
- ✅ Application questions working
- ✅ Vocab/concept phases working
- ✅ SRS algorithm implemented
- ✅ Analytics tracking implemented

### Not Yet Tested
- ❓ Exam Only routing (no exam event data)
- ❓ Principles event routing (no principles data in dev)
- ❓ Roleplay every 7 KPIs (haven't tested that far)
- ❓ Session persistence (can user return later?)
- ❓ Cross-device mastery sync (multiple browsers)

### Deferred to v2
- Confidence tracking
- Reflection prompts
- Knowledge graphs
- Advanced mastery formulas
- Spaced repetition visualizations

---

## Risk Assessment

### Low Risk (Can deploy after QA pass)
- Single KPI session flow
- Question answering mechanics
- Basic analytics recording
- Session summary display

### Medium Risk (Needs verification)
- SRS interval calculations (could affect spacing)
- Multi-session mastery progression
- Event routing for non-Finance events
- Database performance at scale

### High Risk (Need production monitoring)
- AI generation reliability (Groq/Gemini uptime)
- Analytics data accuracy (auditable)
- Session persistence (no data loss)

---

## Success Criteria

### Complete Success
- ✅ All 10 punch items complete
- ✅ No crashes observed
- ✅ Analytics data accurate
- ✅ SRS calculations correct
- ✅ Mobile layout works
- ✅ <1% error rate on question generation

### Acceptable for Deployment
- ✅ 9/10 punch items complete
- ✅ <5% user-reported issues
- ✅ Analytics accurate within ±1%
- ✅ <3% generation failures

### Needs More Work
- ✅ <8/10 punch items
- ✅ Crashes or data loss observed
- ✅ Analytics errors >5%
- ✅ Generation failures >5%

---

## Timeline

**Today (June 8)**
- ✅ Code QA completed
- ✅ Punch list created

**Tomorrow (June 9)**
- [ ] Get authenticated test user set up
- [ ] Complete tests 1-3 (Exam, Principles, TDM flows)
- [ ] Verify analytics for 2-3 sessions

**June 10**
- [ ] Complete tests 4-7 (session, summary, SRS, analytics)
- [ ] Edge case testing (tests 8-10)
- [ ] Mobile testing

**June 11**
- [ ] Production readiness review
- [ ] Finalize recommendation

---

## Notes for Tester

1. **Expect 5-7 second delays** on first question generation (AI is being called)
2. **Session IDs are tracked** - check logs if needed
3. **Malformed questions should NOT crash** - they should be caught
4. **Accuracy % calculated as**: (correct answers) / (total answered) * 100
5. **SRS ease factor starts at 2.5** and adjusts based on performance

---

*This punch list ensures Learn Mode is thoroughly tested before users depend on it.*

*Focus on accuracy of core metrics (analytics, SRS) more than UI polish.*

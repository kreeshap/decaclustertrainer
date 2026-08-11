# Beta data architecture

This document is the Phase 0/1 source of truth. The beta supports only:

- `accounting_application_series`
- `business_finance_series`
- `financial_services_tdm`

## Authorities

| Concept | Authority | Key / isolation |
|---|---|---|
| Selected event | `profiles.default_event_id` | one canonical `deca_events.id` per user |
| Event display name | `deca_events.name` | derived; `profiles.default_event` is compatibility/display data |
| Shared generated questions | `kpi_questions` | `(event_id, kpi_code, question_type, question_slot)` |
| Answer history | `responses` | append-only UUID rows; every row has user, event, question, KPI, session, timestamp |
| Current SRS state | `user_srs_state` | `(user_id, event_id, question_id)` |
| KPI mastery | `user_kpi_mastery` | derived/cache, `(user_id, event_id, kpi_code)` |
| Study sessions | `user_study_sessions` | one user and one event per session |
| Daily activity | `user_daily_activity` | `(user_id, event_id, activity_date)`; global streaks may aggregate these rows |
| Adaptive inference | `kpi_inference_state` | `(user_id, event_id, kpi_code)` |
| Timing baseline | `user_timing_profile` | `(user_id, event_id, question_type, kpi_cluster)` |
| Calibration telemetry | `learning_evaluation_log` | optional to the learning loop, retained because evaluation routes use it |

`user_question_results` and `user_progress` are legacy compatibility tables. They are not read or written by the active answer/resume flow and must not become competing progress authorities. They are deliberately preserved for a later, separately reviewed cleanup migration.

`system_announcements` is admin infrastructure rather than part of the beta learning loop. It is included in the reproducible schema because the existing admin route queries it; students receive no direct table access.

## Security contract

Student-owned tables use RLS keyed to `(select auth.uid())`. Students may read shared beta event/question content, but generated-question writes remain service-role-only. Answer history is append-only for students. Service-role access is limited to backend operations that create shared questions or perform administration.

## Migration and backfill

`0011_beta_schema_reconciliation.sql` is additive and idempotent. It converges the historical migration chain and the inspected live state without dropping data. Existing profiles receive `default_event_id = NULL`; the app must send them through event selection rather than inventing a preference. Run `scripts/verify_beta_schema.py` in CI and `supabase/verify_beta_schema.sql` against every migrated database.

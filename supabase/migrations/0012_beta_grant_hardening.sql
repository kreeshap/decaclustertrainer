-- Remove project-default table privileges and re-grant only the beta API contract.

revoke all on table public.deca_events, public.kpi_questions,
  public.profiles, public.user_progress, public.user_question_results,
  public.responses, public.user_srs_state, public.user_kpi_mastery,
  public.user_study_sessions, public.user_daily_activity,
  public.kpi_inference_state, public.user_timing_profile,
  public.learning_evaluation_log, public.question_reports,
  public.system_announcements, public.v_due_questions
from anon, authenticated;

grant select on table public.deca_events, public.kpi_questions,
  public.v_due_questions to authenticated;

grant select, insert, update on table public.profiles,
  public.user_question_results, public.user_srs_state,
  public.user_kpi_mastery, public.user_study_sessions,
  public.user_daily_activity, public.kpi_inference_state,
  public.user_timing_profile, public.learning_evaluation_log,
  public.question_reports to authenticated;

grant select, insert on table public.responses to authenticated;
grant select, delete on table public.user_progress to authenticated;

-- Phase 1 advisor remediation and convergence cleanup.

alter function public.set_profiles_updated_at() set search_path = public;
revoke execute on function public.handle_new_auth_user() from public, anon, authenticated;
revoke execute on function public.handle_auth_user_update() from public, anon, authenticated;

drop policy if exists "Profiles are insertable by the auth trigger" on public.profiles;
drop policy if exists "Profiles are readable by their owner" on public.profiles;
drop policy if exists "Profiles are updatable by their owner" on public.profiles;

drop index if exists public.uq_questions_event_kpi_type_slot;
drop index if exists public.uq_daily_user_event_date;
drop index if exists public.uq_mastery_user_event_kpi;
drop index if exists public.uq_srs_user_event_question;

drop policy if exists system_announcements_deny_students on public.system_announcements;
create policy system_announcements_deny_students on public.system_announcements
  for all to authenticated using (false) with check (false);

create index if not exists idx_profiles_default_event on public.profiles(default_event_id);
create index if not exists idx_inference_event on public.kpi_inference_state(event_id);
create index if not exists idx_evaluation_event on public.learning_evaluation_log(event_id);
create index if not exists idx_question_reports_user on public.question_reports(user_id);
create index if not exists idx_question_reports_question on public.question_reports(question_id);
create index if not exists idx_responses_event on public.responses(event_id);
create index if not exists idx_responses_question_event on public.responses(question_id,event_id);
create index if not exists idx_responses_session_owner_event on public.responses(session_id,user_id,event_id);
create index if not exists idx_daily_event on public.user_daily_activity(event_id);
create index if not exists idx_mastery_event on public.user_kpi_mastery(event_id);
create index if not exists idx_progress_user on public.user_progress(user_id);
create index if not exists idx_question_results_question on public.user_question_results(question_id);
create index if not exists idx_srs_event on public.user_srs_state(event_id);
create index if not exists idx_srs_question_event on public.user_srs_state(question_id,event_id);
create index if not exists idx_sessions_event on public.user_study_sessions(event_id);
create index if not exists idx_timing_event on public.user_timing_profile(event_id);

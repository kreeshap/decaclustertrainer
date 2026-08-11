-- Phase 1 beta schema reconciliation.
-- Additive/idempotent: converges both the historic migration chain and the
-- inspected live database (which currently contains only public.profiles).

create extension if not exists pgcrypto;

create table if not exists public.deca_events (
  id text primary key,
  name text not null unique,
  cluster text not null,
  is_beta boolean not null default false
);
insert into public.deca_events (id, name, cluster, is_beta) values
  ('accounting_application_series', 'Accounting Application Series', 'Finance', true),
  ('business_finance_series', 'Business Finance Series', 'Finance', true),
  ('financial_services_tdm', 'Financial Services Team Decision Making', 'Finance', true)
on conflict (id) do update set name=excluded.name, cluster=excluded.cluster, is_beta=excluded.is_beta;

alter table public.profiles add column if not exists default_event text not null default '';
alter table public.profiles add column if not exists default_event_id text;
alter table public.profiles drop constraint if exists profiles_default_event_id_fkey;
alter table public.profiles add constraint profiles_default_event_id_fkey
  foreign key (default_event_id) references public.deca_events(id);

create table if not exists public.kpi_questions (
  id uuid primary key default gen_random_uuid(), kpi_code text not null,
  kpi_text text not null default '', kpi_cluster text not null default '',
  deca_cluster text not null default '', event_id text not null references public.deca_events(id),
  question_type text not null default 'recognition', question_slot integer not null default 0,
  question_text text not null, choices jsonb not null default '[]'::jsonb,
  correct_index integer not null check (correct_index between 0 and 3),
  explanation text not null default '', answer_reveal jsonb not null default '{}'::jsonb,
  quality_state jsonb not null default '{}'::jsonb, created_at timestamptz not null default now(),
  unique (event_id, kpi_code, question_type, question_slot)
);
alter table public.kpi_questions add column if not exists question_type text not null default 'recognition';
alter table public.kpi_questions add column if not exists question_slot integer not null default 0;
alter table public.kpi_questions add column if not exists answer_reveal jsonb not null default '{}'::jsonb;
alter table public.kpi_questions add column if not exists quality_state jsonb not null default '{}'::jsonb;
with slots as (
  select id, row_number() over(partition by event_id,kpi_code,question_type order by created_at,id)-1 as slot
  from public.kpi_questions
)
update public.kpi_questions q set question_slot=slots.slot from slots where q.id=slots.id;
create unique index if not exists uq_questions_event_kpi_type_slot on public.kpi_questions(event_id,kpi_code,question_type,question_slot);
create unique index if not exists uq_questions_id_event on public.kpi_questions(id,event_id);
alter table public.kpi_questions drop constraint if exists kpi_questions_event_id_fkey;
alter table public.kpi_questions add constraint kpi_questions_event_id_fkey foreign key (event_id) references public.deca_events(id);
alter table public.kpi_questions alter column event_id drop default;
create index if not exists idx_questions_event_kpi_type on public.kpi_questions(event_id,kpi_code,question_type);

-- Compatibility tables remain available but are not authoritative in the beta.
create table if not exists public.user_progress (
  id uuid primary key default gen_random_uuid(), user_id uuid not null references auth.users(id) on delete cascade,
  item_type text not null check(item_type in ('question','roleplay')), item_id text not null,
  correct boolean, score integer, answered_at timestamptz not null default now()
);
create table if not exists public.user_question_results (
  id uuid primary key default gen_random_uuid(), user_id uuid not null references auth.users(id) on delete cascade,
  question_id uuid not null references public.kpi_questions(id) on delete cascade,
  correct boolean not null default false, answered_at timestamptz not null default now(), unique(user_id,question_id)
);

create table if not exists public.responses (
  id uuid primary key default gen_random_uuid(), user_id uuid not null references auth.users(id) on delete cascade,
  event_id text not null references public.deca_events(id), session_id uuid not null,
  question_id uuid not null references public.kpi_questions(id) on delete restrict,
  kpi_code text not null, question_type text not null, selected_index integer,
  correct boolean not null, response_time_ms integer not null default 0,
  time_to_first_ms integer, answer_changed boolean not null default false,
  answer_change_count integer not null default 0, instant_confidence numeric(6,5),
  is_valid boolean not null default true, idempotency_hash text not null unique,
  answered_at timestamptz not null default now()
);

create table if not exists public.user_srs_state (
  id uuid primary key default gen_random_uuid(), user_id uuid not null references auth.users(id) on delete cascade,
  event_id text not null references public.deca_events(id), question_id uuid not null references public.kpi_questions(id) on delete cascade,
  ease_factor numeric(4,2) not null default 2.50 check(ease_factor >= 1.30), interval_days integer not null default 0 check(interval_days >= 0),
  repetitions integer not null default 0 check(repetitions >= 0), last_quality smallint check(last_quality between 0 and 5),
  last_reviewed timestamptz, next_review timestamptz not null default now(), total_attempts integer not null default 0,
  correct_attempts integer not null default 0, unique(user_id,event_id,question_id)
);
alter table public.user_srs_state add column if not exists event_id text;
update public.user_srs_state s set event_id=q.event_id from public.kpi_questions q where s.question_id=q.id and s.event_id is null;
alter table public.user_srs_state alter column event_id set not null;
alter table public.user_srs_state drop constraint if exists user_srs_state_user_id_question_id_key;
alter table public.user_srs_state drop constraint if exists user_srs_state_event_id_fkey;
alter table public.user_srs_state add constraint user_srs_state_event_id_fkey foreign key(event_id) references public.deca_events(id);
alter table public.user_srs_state drop constraint if exists user_srs_state_question_id_fkey;
alter table public.user_srs_state add constraint user_srs_state_question_event_fkey foreign key(question_id,event_id) references public.kpi_questions(id,event_id) on delete cascade;
create unique index if not exists uq_srs_user_event_question on public.user_srs_state(user_id,event_id,question_id);

create table if not exists public.user_kpi_mastery (
  id uuid primary key default gen_random_uuid(), user_id uuid not null references auth.users(id) on delete cascade,
  event_id text not null references public.deca_events(id), kpi_code text not null, kpi_cluster text not null default '', deca_cluster text not null default '',
  mastery_score numeric(5,2) not null default 0 check(mastery_score between 0 and 100), questions_seen integer not null default 0,
  questions_mastered integer not null default 0, total_questions integer not null default 0,
  last_studied timestamptz, next_review timestamptz, unique(user_id,event_id,kpi_code)
);
alter table public.user_kpi_mastery drop constraint if exists user_kpi_mastery_user_id_kpi_code_key;
alter table public.user_kpi_mastery drop constraint if exists user_kpi_mastery_event_id_fkey;
alter table public.user_kpi_mastery add constraint user_kpi_mastery_event_id_fkey foreign key(event_id) references public.deca_events(id);
alter table public.user_kpi_mastery alter column event_id drop default;
create unique index if not exists uq_mastery_user_event_kpi on public.user_kpi_mastery(user_id,event_id,kpi_code);

create table if not exists public.user_study_sessions (
  id uuid primary key default gen_random_uuid(), user_id uuid not null references auth.users(id) on delete cascade,
  event_id text not null references public.deca_events(id), session_type text not null default 'full', started_at timestamptz not null default now(),
  ended_at timestamptz, duration_seconds integer, kpis_studied integer not null default 0, questions_answered integer not null default 0,
  questions_correct integer not null default 0, vocab_total integer not null default 0, vocab_correct integer not null default 0,
  roleplay_score smallint, accuracy_pct numeric(5,2), ar_answers jsonb not null default '[]'::jsonb
);
alter table public.user_study_sessions add column if not exists ar_answers jsonb not null default '[]'::jsonb;
alter table public.user_study_sessions drop constraint if exists user_study_sessions_event_id_fkey;
alter table public.user_study_sessions add constraint user_study_sessions_event_id_fkey foreign key(event_id) references public.deca_events(id);
alter table public.user_study_sessions alter column event_id drop default;
create unique index if not exists uq_sessions_id_user_event on public.user_study_sessions(id,user_id,event_id);
alter table public.responses drop constraint if exists responses_session_id_fkey;
alter table public.responses add constraint responses_session_owner_event_fkey foreign key(session_id,user_id,event_id) references public.user_study_sessions(id,user_id,event_id);
alter table public.responses drop constraint if exists responses_question_id_fkey;
alter table public.responses add constraint responses_question_event_fkey foreign key(question_id,event_id) references public.kpi_questions(id,event_id) on delete restrict;

create table if not exists public.user_daily_activity (
  id uuid primary key default gen_random_uuid(), user_id uuid not null references auth.users(id) on delete cascade,
  event_id text not null references public.deca_events(id), activity_date date not null default current_date,
  questions_answered integer not null default 0, questions_correct integer not null default 0,
  kpis_studied integer not null default 0, minutes_studied integer not null default 0, unique(user_id,event_id,activity_date)
);
alter table public.user_daily_activity add column if not exists event_id text;
alter table public.user_daily_activity alter column event_id set not null;
alter table public.user_daily_activity drop constraint if exists user_daily_activity_user_id_activity_date_key;
alter table public.user_daily_activity drop constraint if exists user_daily_activity_event_id_fkey;
alter table public.user_daily_activity add constraint user_daily_activity_event_id_fkey foreign key(event_id) references public.deca_events(id);
create unique index if not exists uq_daily_user_event_date on public.user_daily_activity(user_id,event_id,activity_date);

create table if not exists public.kpi_inference_state (
  id uuid primary key default gen_random_uuid(), user_id uuid not null references auth.users(id) on delete cascade,
  event_id text not null references public.deca_events(id), kpi_code text not null,
  mastery_prob numeric(6,5) not null default .5, recognition_mastery numeric(6,5) not null default .5,
  application_mastery numeric(6,5) not null default .5, confidence_est numeric(6,5) not null default .5,
  last_instant_confidence numeric(6,5), uncertainty numeric(6,5), sample_count integer not null default 0,
  last_updated timestamptz not null default now(), unique(user_id,event_id,kpi_code)
);
create table if not exists public.user_timing_profile (
  id uuid primary key default gen_random_uuid(), user_id uuid not null references auth.users(id) on delete cascade,
  event_id text not null references public.deca_events(id), question_type text not null, kpi_cluster text not null default '',
  median_ms integer not null default 12000, sample_count integer not null default 0, updated_at timestamptz not null default now(),
  unique(user_id,event_id,question_type,kpi_cluster)
);
create table if not exists public.learning_evaluation_log (
  id uuid primary key default gen_random_uuid(), user_id uuid not null references auth.users(id) on delete cascade,
  event_id text not null references public.deca_events(id), kpi_code text not null, kpi_cluster text not null default '', question_type text not null,
  recognition_mastery numeric(6,5), application_mastery numeric(6,5), predicted_mastery numeric(6,5), confidence_est numeric(6,5),
  instant_confidence numeric(6,5), volatility numeric(6,5), uncertainty numeric(6,5), correct boolean not null,
  response_time_ms integer not null default 0, recorded_at timestamptz not null default now()
);
create table if not exists public.system_announcements (
  id uuid primary key default gen_random_uuid(), title text not null, message text not null,
  type text not null default 'info', created_at timestamptz not null default now()
);
create table if not exists public.question_reports (
  id uuid primary key default gen_random_uuid(), user_id uuid not null references auth.users(id) on delete cascade,
  question_id uuid not null references public.kpi_questions(id) on delete cascade, kpi_code text not null default '',
  question_type text not null default 'recognition', reason text not null, details text not null default '',
  benchmark jsonb not null default '{}'::jsonb, created_at timestamptz not null default now()
);

-- Historic migrations omitted auth-user foreign keys on several tables.
alter table public.user_question_results drop constraint if exists user_question_results_user_id_fkey;
alter table public.user_question_results add constraint user_question_results_user_id_fkey foreign key(user_id) references auth.users(id) on delete cascade;
alter table public.user_srs_state drop constraint if exists user_srs_state_user_id_fkey;
alter table public.user_srs_state add constraint user_srs_state_user_id_fkey foreign key(user_id) references auth.users(id) on delete cascade;
alter table public.user_kpi_mastery drop constraint if exists user_kpi_mastery_user_id_fkey;
alter table public.user_kpi_mastery add constraint user_kpi_mastery_user_id_fkey foreign key(user_id) references auth.users(id) on delete cascade;
alter table public.user_study_sessions drop constraint if exists user_study_sessions_user_id_fkey;
alter table public.user_study_sessions add constraint user_study_sessions_user_id_fkey foreign key(user_id) references auth.users(id) on delete cascade;
alter table public.user_daily_activity drop constraint if exists user_daily_activity_user_id_fkey;
alter table public.user_daily_activity add constraint user_daily_activity_user_id_fkey foreign key(user_id) references auth.users(id) on delete cascade;

create index if not exists idx_responses_resume on public.responses(user_id,event_id,answered_at desc);
create index if not exists idx_srs_due on public.user_srs_state(user_id,event_id,next_review);
create index if not exists idx_mastery_resume on public.user_kpi_mastery(user_id,event_id,mastery_score,next_review);
create index if not exists idx_sessions_resume on public.user_study_sessions(user_id,event_id,started_at desc);
create index if not exists idx_daily_resume on public.user_daily_activity(user_id,event_id,activity_date desc);
create index if not exists idx_eval_user_event on public.learning_evaluation_log(user_id,event_id,recorded_at desc);

create or replace view public.v_due_questions with (security_invoker=true) as
select s.user_id,s.event_id,s.question_id,s.ease_factor,s.interval_days,s.repetitions,s.next_review,
       s.total_attempts,s.correct_attempts,q.kpi_code,q.kpi_text,q.kpi_cluster,q.deca_cluster,
       q.question_type,q.question_text,q.choices,q.correct_index,q.explanation
from public.user_srs_state s join public.kpi_questions q on q.id=s.question_id and q.event_id=s.event_id
where s.next_review <= now();

-- RLS: students own their rows; shared content is read-only; admin tables are service-role only.
do $$ declare t text; begin
  foreach t in array array['profiles','user_progress','user_question_results','responses','user_srs_state','user_kpi_mastery','user_study_sessions','user_daily_activity','kpi_inference_state','user_timing_profile','learning_evaluation_log','question_reports'] loop
    execute format('alter table public.%I enable row level security',t);
    execute format('drop policy if exists %I on public.%I',t||'_select_own',t);
    execute format('drop policy if exists %I on public.%I',t||'_insert_own',t);
    execute format('drop policy if exists %I on public.%I',t||'_update_own',t);
    execute format('create policy %I on public.%I for select to authenticated using ((select auth.uid()) = %I)',t||'_select_own',t,case when t='profiles' then 'id' else 'user_id' end);
    execute format('create policy %I on public.%I for insert to authenticated with check ((select auth.uid()) = %I)',t||'_insert_own',t,case when t='profiles' then 'id' else 'user_id' end);
    execute format('create policy %I on public.%I for update to authenticated using ((select auth.uid()) = %I) with check ((select auth.uid()) = %I)',t||'_update_own',t,case when t='profiles' then 'id' else 'user_id' end,case when t='profiles' then 'id' else 'user_id' end);
  end loop;
end $$;
alter table public.deca_events enable row level security;
alter table public.kpi_questions enable row level security;
alter table public.system_announcements enable row level security;
drop policy if exists deca_events_beta_read on public.deca_events;
create policy deca_events_beta_read on public.deca_events for select to authenticated using(is_beta);
drop policy if exists kpi_questions_read on public.kpi_questions;
create policy kpi_questions_read on public.kpi_questions for select to authenticated using(true);
drop policy if exists responses_update_own on public.responses;
drop policy if exists user_progress_insert_own on public.user_progress;
drop policy if exists user_progress_update_own on public.user_progress;
drop policy if exists user_progress_delete_own on public.user_progress;
create policy user_progress_delete_own on public.user_progress for delete to authenticated using((select auth.uid())=user_id);

-- Since 2026, new public tables are not implicitly exposed by Supabase's Data API.
grant usage on schema public to authenticated, service_role;
grant select on public.deca_events,public.kpi_questions,public.v_due_questions to authenticated;
grant select,insert,update on public.profiles,public.user_progress,public.user_question_results,public.responses,
  public.user_srs_state,public.user_kpi_mastery,public.user_study_sessions,public.user_daily_activity,
  public.kpi_inference_state,public.user_timing_profile,public.learning_evaluation_log,public.question_reports to authenticated;
grant all on all tables in schema public to service_role;
revoke update,delete on public.responses from authenticated;
revoke insert,update on public.user_progress from authenticated;
grant delete on public.user_progress to authenticated;

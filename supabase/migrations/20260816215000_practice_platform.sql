alter table public.kpi_questions
  add column if not exists designed_difficulty text not null default 'medium'
    check (designed_difficulty in ('easy','medium','hard')),
  add column if not exists empirical_difficulty text,
  add column if not exists question_style text not null default 'application';

create table if not exists public.practice_sets (
  id uuid primary key default gen_random_uuid(), user_id uuid not null, event_id text not null,
  title text not null, set_type text not null check(set_type in ('smart','custom','mock')),
  mode text not null check(mode in ('tutor','exam','mock')), filters jsonb not null default '{}'::jsonb,
  status text not null default 'active' check(status in ('active','completed','abandoned')),
  question_count integer not null, current_index integer not null default 0,
  time_limit_seconds integer, started_at timestamptz not null default now(), completed_at timestamptz,
  duration_seconds integer, created_at timestamptz not null default now()
);

create table if not exists public.practice_set_questions (
  id uuid primary key default gen_random_uuid(), practice_set_id uuid not null references public.practice_sets(id) on delete cascade,
  user_id uuid not null, question_id uuid not null references public.kpi_questions(id) on delete cascade,
  position integer not null, selected_index integer, correct boolean, flagged boolean not null default false,
  response_time_ms integer, answered_at timestamptz, created_at timestamptz not null default now(),
  unique(practice_set_id,position), unique(practice_set_id,question_id)
);

create table if not exists public.question_flags (
  user_id uuid not null, event_id text not null, question_id uuid not null references public.kpi_questions(id) on delete cascade,
  flagged_at timestamptz not null default now(), primary key(user_id,event_id,question_id)
);

alter table public.responses add column if not exists practice_set_id uuid references public.practice_sets(id) on delete set null;
create index if not exists idx_practice_sets_resume on public.practice_sets(user_id,event_id,status,created_at desc);
create index if not exists idx_practice_set_questions_order on public.practice_set_questions(practice_set_id,position);
create index if not exists idx_practice_set_questions_question on public.practice_set_questions(question_id);
create index if not exists idx_question_flags_user on public.question_flags(user_id,event_id);
create index if not exists idx_question_flags_question on public.question_flags(question_id);
create index if not exists idx_responses_practice_set on public.responses(practice_set_id);

do $$ declare t text; begin
  foreach t in array array['practice_sets','practice_set_questions','question_flags'] loop
    execute format('alter table public.%I enable row level security',t);
    execute format('drop policy if exists %I on public.%I',t||'_select_own',t);
    execute format('drop policy if exists %I on public.%I',t||'_insert_own',t);
    execute format('drop policy if exists %I on public.%I',t||'_update_own',t);
    execute format('drop policy if exists %I on public.%I',t||'_delete_own',t);
    execute format('create policy %I on public.%I for select to authenticated using ((select auth.uid())=user_id)',t||'_select_own',t);
    execute format('create policy %I on public.%I for insert to authenticated with check ((select auth.uid())=user_id)',t||'_insert_own',t);
    execute format('create policy %I on public.%I for update to authenticated using ((select auth.uid())=user_id) with check ((select auth.uid())=user_id)',t||'_update_own',t);
    execute format('create policy %I on public.%I for delete to authenticated using ((select auth.uid())=user_id)',t||'_delete_own',t);
  end loop;
end $$;
grant select,insert,update,delete on public.practice_sets,public.practice_set_questions,public.question_flags to authenticated;
grant all on public.practice_sets,public.practice_set_questions,public.question_flags to service_role;

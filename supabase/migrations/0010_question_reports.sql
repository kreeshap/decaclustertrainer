-- Question reports: user-submitted flags for bad or confusing questions.
-- Run in the Supabase SQL Editor.

create table if not exists public.question_reports (
  id             uuid        primary key default gen_random_uuid(),
  user_id        uuid        not null references auth.users (id) on delete cascade,
  question_id    uuid        not null references public.kpi_questions (id) on delete cascade,
  kpi_code       text        not null default '',
  question_type  text        not null default 'recognition'
    check (question_type in ('recognition', 'application')),
  reason         text        not null,
  details        text        not null default '',
  benchmark      jsonb       not null default '{}'::jsonb,
  created_at     timestamptz not null default timezone('utc', now())
);

create index if not exists question_reports_user_id_idx on public.question_reports (user_id);
create index if not exists question_reports_question_id_idx on public.question_reports (question_id);
create index if not exists question_reports_created_at_idx on public.question_reports (created_at desc);

alter table public.question_reports enable row level security;

create policy "Question reports readable by owner"
  on public.question_reports for select
  to authenticated using (auth.uid() = user_id);

create policy "Question reports insertable by owner"
  on public.question_reports for insert
  to authenticated with check (auth.uid() = user_id);


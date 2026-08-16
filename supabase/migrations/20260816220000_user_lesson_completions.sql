create table if not exists public.user_lesson_completions (
  user_id uuid not null references auth.users(id) on delete cascade,
  event_id text not null references public.deca_events(id),
  kpi_code text not null,
  lesson_version integer not null,
  completed_at timestamptz not null default now(),
  primary key (user_id, event_id, kpi_code, lesson_version)
);

create index idx_user_lesson_completions_event
  on public.user_lesson_completions (user_id, event_id, completed_at desc);

alter table public.user_lesson_completions enable row level security;
create policy user_lesson_completions_select_own
  on public.user_lesson_completions for select to authenticated
  using ((select auth.uid()) = user_id);
create policy user_lesson_completions_insert_own
  on public.user_lesson_completions for insert to authenticated
  with check ((select auth.uid()) = user_id);
create policy user_lesson_completions_update_own
  on public.user_lesson_completions for update to authenticated
  using ((select auth.uid()) = user_id)
  with check ((select auth.uid()) = user_id);

revoke all on table public.user_lesson_completions from anon;
grant select, insert, update on table public.user_lesson_completions to authenticated;
grant select, insert, update, delete on table public.user_lesson_completions to service_role;

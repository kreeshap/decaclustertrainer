create table if not exists public.user_adaptive_state (
  user_id uuid not null references auth.users(id) on delete cascade,
  event_id text not null references public.deca_events(id) on delete cascade,
  state jsonb not null default '{}'::jsonb,
  computed_at timestamptz not null default now(),
  primary key (user_id, event_id)
);

create table if not exists public.user_today_plans (
  user_id uuid not null references auth.users(id) on delete cascade,
  event_id text not null references public.deca_events(id) on delete cascade,
  plan_date date not null default current_date,
  time_budget_minutes integer not null check (time_budget_minutes between 1 and 180),
  tasks jsonb not null default '[]'::jsonb,
  rationale text not null default '',
  inputs jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  primary key (user_id, event_id, plan_date)
);

create index if not exists idx_today_plans_user_date
  on public.user_today_plans (user_id, plan_date desc);

alter table public.user_adaptive_state enable row level security;
alter table public.user_today_plans enable row level security;

create policy user_adaptive_state_select_own on public.user_adaptive_state
  for select to authenticated using ((select auth.uid()) = user_id);
create policy user_adaptive_state_insert_own on public.user_adaptive_state
  for insert to authenticated with check ((select auth.uid()) = user_id);
create policy user_adaptive_state_update_own on public.user_adaptive_state
  for update to authenticated using ((select auth.uid()) = user_id)
  with check ((select auth.uid()) = user_id);

create policy user_today_plans_select_own on public.user_today_plans
  for select to authenticated using ((select auth.uid()) = user_id);
create policy user_today_plans_insert_own on public.user_today_plans
  for insert to authenticated with check ((select auth.uid()) = user_id);
create policy user_today_plans_update_own on public.user_today_plans
  for update to authenticated using ((select auth.uid()) = user_id)
  with check ((select auth.uid()) = user_id);

revoke all on table public.user_adaptive_state, public.user_today_plans from anon;
grant select, insert, update on table public.user_adaptive_state, public.user_today_plans to authenticated;
grant all on table public.user_adaptive_state, public.user_today_plans to service_role;

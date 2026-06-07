-- User progress table: stores every question attempt and roleplay score.
-- Run in Supabase SQL Editor.

create table if not exists public.user_progress (
  id          uuid        primary key default gen_random_uuid(),
  user_id     uuid        not null references auth.users (id) on delete cascade,
  item_type   text        not null check (item_type in ('question', 'roleplay')),
  item_id     text        not null,
  correct     boolean,
  score       integer,
  answered_at timestamptz not null default timezone('utc', now())
);

create index if not exists user_progress_user_id_idx on public.user_progress (user_id);

alter table public.user_progress enable row level security;

create policy "Progress readable by owner"
  on public.user_progress for select
  to authenticated using (auth.uid() = user_id);

create policy "Progress insertable by owner"
  on public.user_progress for insert
  to authenticated with check (auth.uid() = user_id);

create policy "Progress deletable by owner"
  on public.user_progress for delete
  to authenticated using (auth.uid() = user_id);

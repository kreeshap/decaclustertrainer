-- Profiles table that mirrors Supabase Auth users.
-- Run this in the Supabase SQL Editor or apply it through your migration flow.

create extension if not exists pgcrypto;

create table if not exists public.profiles (
  id uuid primary key references auth.users (id) on delete cascade,
  display_name text,
  email text not null unique,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now())
);

alter table public.profiles enable row level security;

create or replace function public.set_profiles_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = timezone('utc', now());
  return new;
end;
$$;

drop trigger if exists set_profiles_updated_at on public.profiles;
create trigger set_profiles_updated_at
before update on public.profiles
for each row
execute function public.set_profiles_updated_at();

create or replace function public.handle_new_auth_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
  profile_display_name text;
begin
  profile_display_name :=
    coalesce(
      new.raw_user_meta_data->>'display_name',
      new.raw_user_meta_data->>'full_name',
      new.raw_user_meta_data->>'name',
      split_part(new.email, '@', 1)
    );

  insert into public.profiles (id, display_name, email)
  values (new.id, profile_display_name, new.email)
  on conflict (id) do update
    set display_name = excluded.display_name,
        email = excluded.email,
        updated_at = timezone('utc', now());

  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
after insert on auth.users
for each row
execute function public.handle_new_auth_user();

create or replace function public.handle_auth_user_update()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  update public.profiles
     set email = new.email,
         display_name = coalesce(
           new.raw_user_meta_data->>'display_name',
           new.raw_user_meta_data->>'full_name',
           new.raw_user_meta_data->>'name',
           display_name
         )
   where id = new.id;

  return new;
end;
$$;

drop trigger if exists on_auth_user_updated on auth.users;
create trigger on_auth_user_updated
after update on auth.users
for each row
execute function public.handle_auth_user_update();

insert into public.profiles (id, display_name, email)
select
  u.id,
  coalesce(
    u.raw_user_meta_data->>'display_name',
    u.raw_user_meta_data->>'full_name',
    u.raw_user_meta_data->>'name',
    split_part(u.email, '@', 1)
  ),
  u.email
from auth.users u
on conflict (id) do nothing;

create policy "Profiles are readable by their owner"
on public.profiles
for select
to authenticated
using (auth.uid() = id);

create policy "Profiles are updatable by their owner"
on public.profiles
for update
to authenticated
using (auth.uid() = id)
with check (auth.uid() = id);

create policy "Profiles are insertable by the auth trigger"
on public.profiles
for insert
to authenticated
with check (auth.uid() = id);

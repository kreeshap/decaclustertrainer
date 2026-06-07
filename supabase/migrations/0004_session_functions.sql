-- Functions to expose auth.sessions to the authenticated user.
-- auth.sessions is in the hidden auth schema, so we use security definer
-- functions callable via PostgREST RPC to read/delete only the caller's rows.
-- Run in the Supabase SQL Editor.

-- Returns the current user's active sessions (max 20, newest first).
create or replace function public.get_my_sessions()
returns table (
  session_id   uuid,
  created_at   timestamptz,
  refreshed_at timestamptz,
  ip_address   text,
  user_agent   text
)
language sql
security definer
set search_path = auth, public
as $$
  select
    id                                        as session_id,
    created_at,
    refreshed_at,
    ip::text                                  as ip_address,
    user_agent
  from auth.sessions
  where user_id = auth.uid()
  order by coalesce(refreshed_at, created_at) desc nulls last
  limit 20;
$$;

grant execute on function public.get_my_sessions() to authenticated;


-- Deletes one of the caller's sessions. Returns true if a row was deleted.
create or replace function public.revoke_my_session(p_session_id uuid)
returns boolean
language plpgsql
security definer
set search_path = auth, public
as $$
declare
  deleted_count integer;
begin
  delete from auth.sessions
  where id = p_session_id
    and user_id = auth.uid();
  get diagnostics deleted_count = row_count;
  return deleted_count > 0;
end;
$$;

grant execute on function public.revoke_my_session(uuid) to authenticated;

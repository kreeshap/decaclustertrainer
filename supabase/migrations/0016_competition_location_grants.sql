-- Harden Data API grants for competition location reference tables.

revoke all on table public.states, public.deca_subdivisions, public.deca_conferences
from anon, authenticated;

grant select on table public.states, public.deca_subdivisions, public.deca_conferences
to authenticated;

-- Applied to production as migration 20260816210853.
create table public.generated_kpi_lessons (
  kpi_id text primary key references public.kpi_catalog(id) on delete cascade,
  lesson jsonb not null,
  status text not null default 'ready' check (status in ('ready', 'blocked')),
  lesson_version integer not null default 4,
  source_audit_id uuid references public.lesson_content_audits(id) on delete set null,
  generated_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index idx_generated_kpi_lessons_status
  on public.generated_kpi_lessons (status, updated_at);

alter table public.generated_kpi_lessons enable row level security;
revoke all on table public.generated_kpi_lessons from anon, authenticated;
grant select, insert, update, delete on table public.generated_kpi_lessons to service_role;

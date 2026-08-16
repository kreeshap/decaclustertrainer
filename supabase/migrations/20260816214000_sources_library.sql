create table if not exists public.reference_sources (
  id uuid primary key default gen_random_uuid(),
  canonical_key text not null unique,
  title text not null default '',
  authors text not null default '',
  edition text not null default '',
  publication_year integer,
  publisher text not null default '',
  raw_citation text not null,
  url text,
  status text not null default 'unreviewed'
    check (status in ('unreviewed','located','accessible','paywalled','physical','unavailable','do_not_use')),
  notes text not null default '',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.question_source_links (
  id uuid primary key default gen_random_uuid(),
  source_id uuid not null references public.reference_sources(id) on delete cascade,
  import_item_id uuid not null references public.question_import_items(id) on delete cascade,
  document_id uuid not null references public.question_source_documents(id) on delete cascade,
  imported_question_id uuid references public.kpi_questions(id) on delete set null,
  kpi_id text references public.kpi_catalog(id) on delete set null,
  kpi_code text not null default '',
  pages text not null default '',
  raw_citation text not null,
  created_at timestamptz not null default now(),
  unique(source_id, import_item_id)
);

create index if not exists idx_question_sources_source on public.question_source_links(source_id, kpi_code);
create index if not exists idx_reference_sources_status on public.reference_sources(status, title);
alter table public.reference_sources enable row level security;
alter table public.question_source_links enable row level security;
revoke all on table public.reference_sources, public.question_source_links from anon, authenticated;
grant select, insert, update, delete on table public.reference_sources, public.question_source_links to service_role;

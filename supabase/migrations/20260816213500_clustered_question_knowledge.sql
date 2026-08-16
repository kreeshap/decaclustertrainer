alter table public.question_import_items
  add column if not exists kpi_cluster text not null default '',
  add column if not exists deca_cluster text not null default '',
  add column if not exists source_references jsonb not null default '[]'::jsonb,
  add column if not exists raw_descriptive_key text not null default '';

create index if not exists idx_question_import_cluster
  on public.question_import_items(deca_cluster, kpi_cluster, kpi_code, review_status);

alter table public.kpi_catalog
  add column if not exists knowledge_version integer not null default 1;

alter table public.generated_kpi_lessons
  drop constraint if exists generated_kpi_lessons_status_check;
alter table public.generated_kpi_lessons
  add constraint generated_kpi_lessons_status_check check (status in ('ready','blocked','stale'));
alter table public.generated_kpi_lessons
  add column if not exists knowledge_version integer not null default 1;

create table if not exists public.kpi_knowledge_items (
  id uuid primary key default gen_random_uuid(),
  kpi_id text not null references public.kpi_catalog(id) on delete cascade,
  kpi_code text not null,
  kpi_cluster text not null default '',
  deca_cluster text not null default '',
  knowledge_type text not null default 'source_explanation'
    check (knowledge_type in ('core_concept','mechanism','distinction','misconception','source_explanation')),
  content text not null,
  importance text not null default 'important'
    check (importance in ('required','important','supporting','question_specific')),
  content_hash text not null,
  source_document_id uuid references public.question_source_documents(id) on delete set null,
  source_import_item_id uuid references public.question_import_items(id) on delete set null,
  source_references jsonb not null default '[]'::jsonb,
  evidence_count integer not null default 1,
  review_status text not null default 'pending' check (review_status in ('pending','approved','ignored')),
  reviewed_by uuid,
  reviewed_at timestamptz,
  created_at timestamptz not null default now(),
  unique(kpi_id, content_hash)
);

create index if not exists idx_kpi_knowledge_review on public.kpi_knowledge_items(review_status, deca_cluster, kpi_cluster, kpi_code);
alter table public.kpi_knowledge_items enable row level security;
revoke all on table public.kpi_knowledge_items from anon, authenticated;
grant select, insert, update, delete on table public.kpi_knowledge_items to service_role;

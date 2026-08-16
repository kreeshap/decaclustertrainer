-- Staged, rights-aware PDF question ingestion. All ingestion tables are server-only.

create table if not exists public.question_source_documents (
  id uuid primary key default gen_random_uuid(),
  filename text not null,
  file_sha256 text not null unique,
  source_type text not null check (source_type in ('deca_sample','owned','licensed','other')),
  usage_rights text not null check (usage_rights in ('reference_only','licensed_for_student_use')),
  career_cluster text not null default '',
  event_id text not null default '',
  exam_year integer,
  page_count integer not null default 0,
  detected_count integer not null default 0,
  ready_count integer not null default 0,
  review_count integer not null default 0,
  duplicate_count integer not null default 0,
  status text not null default 'processing' check (status in ('processing','review','complete','failed')),
  failure_reason text,
  created_by uuid,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.question_import_items (
  id uuid primary key default gen_random_uuid(),
  document_id uuid not null references public.question_source_documents(id) on delete cascade,
  question_number integer not null,
  page_number integer,
  question_text text not null,
  choices jsonb not null default '[]'::jsonb,
  correct_index integer check (correct_index between 0 and 3),
  explanation text not null default '',
  kpi_code text not null default '',
  kpi_source text not null default 'document' check (kpi_source in ('document','admin','ai_inferred','unknown')),
  instructional_area text not null default '',
  rigor text not null default '',
  normalized_hash text not null,
  duplicate_question_id uuid references public.kpi_questions(id) on delete set null,
  similarity numeric(5,4),
  review_reasons jsonb not null default '[]'::jsonb,
  review_status text not null default 'pending' check (review_status in ('ready','pending','approved','skipped','imported')),
  imported_question_id uuid references public.kpi_questions(id) on delete set null,
  reviewed_by uuid,
  reviewed_at timestamptz,
  created_at timestamptz not null default now(),
  unique(document_id, question_number)
);

alter table public.kpi_questions
  add column if not exists source_type text not null default 'ai_generated',
  add column if not exists source_document_id uuid references public.question_source_documents(id) on delete set null,
  add column if not exists source_question_number integer,
  add column if not exists source_page integer,
  add column if not exists usage_rights text not null default 'app_authored',
  add column if not exists normalized_hash text,
  add column if not exists review_status text not null default 'approved';

alter table public.kpi_questions drop constraint if exists kpi_questions_beta_type_slot_check;

create index if not exists idx_question_import_review on public.question_import_items(review_status, created_at);
create index if not exists idx_question_import_hash on public.question_import_items(normalized_hash);
create index if not exists idx_kpi_questions_normalized_hash on public.kpi_questions(normalized_hash);

alter table public.question_source_documents enable row level security;
alter table public.question_import_items enable row level security;
revoke all on table public.question_source_documents, public.question_import_items from anon, authenticated;
grant select, insert, update, delete on table public.question_source_documents, public.question_import_items to service_role;

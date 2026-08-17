-- Practice Corpus v1: private, provenance-preserving benchmark ingestion.

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('practice-corpus-private', 'practice-corpus-private', false, 26214400, array['application/pdf'])
on conflict (id) do update set public=false, file_size_limit=excluded.file_size_limit,
  allowed_mime_types=excluded.allowed_mime_types;

create table public.practice_corpus_documents (
  id uuid primary key default gen_random_uuid(),
  content_type text not null check (content_type in ('exam','roleplay')),
  title text not null,
  competitive_year text,
  cluster text not null default '',
  event_codes jsonb not null default '[]'::jsonb,
  event_type text check (event_type is null or event_type in ('individual_series','team_decision_making')),
  competition_level text not null default 'practice_sample'
    check (competition_level in ('district','association','icdc','practice_sample')),
  instructional_area text not null default '',
  source_name text not null default '',
  source_url text,
  source_organization text not null default '',
  rights_status text not null default 'unknown'
    check (rights_status in ('unknown','reference_only','owned','licensed_for_student_use','public_domain','do_not_use')),
  official_deca boolean not null default false,
  notes text not null default '',
  original_filename text not null,
  storage_bucket text not null default 'practice-corpus-private',
  storage_path text not null unique,
  file_sha256 text not null unique,
  normalized_text_hash text not null,
  similarity_fingerprint text not null,
  extracted_text text not null default '',
  metadata_suggestions jsonb not null default '{}'::jsonb,
  confirmed_metadata jsonb not null default '{}'::jsonb,
  parser_version text not null,
  extraction_version integer not null default 1,
  processing_state text not null default 'uploaded'
    check (processing_state in ('uploaded','parsed','needs_review','verified_reference','failed')),
  benchmark_eligible boolean not null default false,
  student_publishable boolean not null default false,
  duplicate_of uuid references public.practice_corpus_documents(id) on delete set null,
  created_by uuid references auth.users(id) on delete set null,
  uploaded_at timestamptz not null default now(),
  parsed_at timestamptz,
  verified_at timestamptz,
  verified_by uuid references auth.users(id) on delete set null,
  updated_at timestamptz not null default now(),
  check (not student_publishable or rights_status in ('owned','licensed_for_student_use','public_domain')),
  check (not benchmark_eligible or processing_state='verified_reference')
);

create table public.reference_exam_questions (
  id uuid primary key default gen_random_uuid(),
  document_id uuid not null references public.practice_corpus_documents(id) on delete cascade,
  question_number integer not null,
  page_number integer,
  stem text not null,
  choices jsonb not null default '[]'::jsonb,
  official_answer integer check (official_answer between 0 and 3),
  explanation text not null default '',
  instructional_area text not null default '',
  pi_code text,
  pi_source text not null default 'unknown' check (pi_source in ('document','human','unknown')),
  cognitive_demand text,
  question_format text not null default 'multiple_choice',
  metrics jsonb not null default '{}'::jsonb,
  normalized_hash text not null,
  duplicate_of uuid references public.reference_exam_questions(id) on delete set null,
  human_verified boolean not null default false,
  verified_at timestamptz,
  verified_by uuid references auth.users(id) on delete set null,
  created_at timestamptz not null default now(),
  unique(document_id, question_number)
);

create table public.reference_roleplays (
  id uuid primary key default gen_random_uuid(),
  document_id uuid not null unique references public.practice_corpus_documents(id) on delete cascade,
  event_code text not null default '',
  event_type text check (event_type is null or event_type in ('individual_series','team_decision_making')),
  instructional_area text not null default '',
  performance_indicators jsonb not null default '[]'::jsonb,
  participant_role text not null default '',
  judge_role text not null default '',
  prep_time_minutes integer,
  presentation_time_minutes integer,
  participant_instructions text not null default '',
  situation text not null default '',
  judge_instructions text not null default '',
  official_tasks jsonb not null default '[]'::jsonb,
  judge_questions jsonb not null default '[]'::jsonb,
  evaluation_criteria text not null default '',
  problem_archetype text,
  participant_authority text,
  expected_action text,
  metrics jsonb not null default '{}'::jsonb,
  raw_sections jsonb not null default '{}'::jsonb,
  human_verified boolean not null default false,
  verified_at timestamptz,
  verified_by uuid references auth.users(id) on delete set null,
  created_at timestamptz not null default now()
);

create table public.corpus_readiness_snapshots (
  id uuid primary key default gen_random_uuid(),
  content_type text not null check (content_type in ('exam','roleplay')),
  event_code text not null default '',
  cluster text not null default '',
  documents integer not null default 0,
  items integer not null default 0,
  years_represented integer not null default 0,
  competition_levels integer not null default 0,
  pi_coverage numeric(6,5),
  readiness_status text not null check (readiness_status in ('insufficient','generator_ready')),
  readiness_reasons jsonb not null default '[]'::jsonb,
  calculated_at timestamptz not null default now()
);

create index practice_corpus_dashboard_idx on public.practice_corpus_documents
  (content_type, processing_state, benchmark_eligible, cluster, competition_level);
create index practice_corpus_normalized_hash_idx on public.practice_corpus_documents(normalized_text_hash);
create index reference_exam_document_idx on public.reference_exam_questions(document_id, human_verified);
create index reference_exam_pi_idx on public.reference_exam_questions(pi_code) where pi_code is not null;
create index reference_roleplay_event_idx on public.reference_roleplays(event_code, instructional_area, human_verified);
create index corpus_readiness_lookup_idx on public.corpus_readiness_snapshots(content_type, event_code, calculated_at desc);

alter table public.practice_corpus_documents enable row level security;
alter table public.reference_exam_questions enable row level security;
alter table public.reference_roleplays enable row level security;
alter table public.corpus_readiness_snapshots enable row level security;

revoke all on public.practice_corpus_documents, public.reference_exam_questions,
  public.reference_roleplays, public.corpus_readiness_snapshots from anon, authenticated;
grant select, insert, update, delete on public.practice_corpus_documents,
  public.reference_exam_questions, public.reference_roleplays,
  public.corpus_readiness_snapshots to service_role;


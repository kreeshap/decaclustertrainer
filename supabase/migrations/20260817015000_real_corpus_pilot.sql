alter table public.practice_corpus_documents
  add column if not exists field_confidence jsonb not null default '{}'::jsonb,
  add column if not exists review_flags jsonb not null default '[]'::jsonb,
  add column if not exists review_priority text not null default 'normal'
    check (review_priority in ('low','normal','high','critical')),
  add column if not exists pilot_audited_at timestamptz,
  add column if not exists pilot_audited_by uuid references auth.users(id) on delete set null;

alter table public.reference_exam_questions
  add column if not exists field_confidence jsonb not null default '{}'::jsonb,
  add column if not exists review_flags jsonb not null default '[]'::jsonb,
  add column if not exists gold_reference boolean not null default false;

alter table public.reference_roleplays
  add column if not exists field_confidence jsonb not null default '{}'::jsonb,
  add column if not exists review_flags jsonb not null default '[]'::jsonb,
  add column if not exists gold_reference boolean not null default false;

create table public.corpus_parser_failures (
  id uuid primary key default gen_random_uuid(),
  document_id uuid not null references public.practice_corpus_documents(id) on delete cascade,
  item_type text not null check (item_type in ('document','exam_question','roleplay')),
  item_id uuid,
  failure_code text not null check (failure_code in (
    'exam_choice_split','exam_answer_key_mismatch','exam_multiline_stem','header_contamination',
    'roleplay_pi_detection','roleplay_section_boundary','roleplay_judge_question_split','metadata_year_unknown',
    'metadata_event_unknown','metadata_competition_level_unknown','table_or_special_format','page_break_split','other'
  )),
  field_name text not null default '',
  detail text not null default '',
  detected_by text not null default 'parser' check (detected_by in ('parser','reviewer')),
  resolved boolean not null default false,
  resolved_at timestamptz,
  resolved_by uuid references auth.users(id) on delete set null,
  created_at timestamptz not null default now()
);

create table public.corpus_style_profile_snapshots (
  id uuid primary key default gen_random_uuid(),
  content_type text not null check (content_type in ('exam','roleplay')),
  event_code text not null default '',
  verified_item_count integer not null,
  checkpoint integer,
  profile jsonb not null,
  previous_snapshot_id uuid references public.corpus_style_profile_snapshots(id) on delete set null,
  stability_delta numeric(8,6),
  calculated_at timestamptz not null default now(),
  unique(content_type,event_code,verified_item_count)
);

create index corpus_parser_failures_queue_idx on public.corpus_parser_failures(resolved,failure_code,created_at);
create index corpus_parser_failures_document_idx on public.corpus_parser_failures(document_id);
create index practice_corpus_pilot_audited_by_idx on public.practice_corpus_documents(pilot_audited_by) where pilot_audited_by is not null;
create index reference_exam_gold_idx on public.reference_exam_questions(document_id) where gold_reference;
create index reference_roleplay_gold_idx on public.reference_roleplays(event_code) where gold_reference;
create index corpus_style_profile_lookup_idx on public.corpus_style_profile_snapshots(content_type,event_code,verified_item_count desc);

alter table public.corpus_parser_failures enable row level security;
alter table public.corpus_style_profile_snapshots enable row level security;
revoke all on public.corpus_parser_failures, public.corpus_style_profile_snapshots from anon, authenticated;
grant select, insert, update, delete on public.corpus_parser_failures, public.corpus_style_profile_snapshots to service_role;

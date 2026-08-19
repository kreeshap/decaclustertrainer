create table public.corpus_parse_attempts (
  id uuid primary key default gen_random_uuid(),
  document_id uuid references public.practice_corpus_documents(id) on delete set null,
  content_type text not null check (content_type in ('exam','roleplay')),
  original_filename text not null,
  status text not null default 'parsing' check (status in ('parsing','succeeded','failed')),
  stage text not null default 'extracting',
  item_count integer not null default 0 check (item_count >= 0),
  error_message text,
  created_by uuid references auth.users(id) on delete set null,
  started_at timestamptz not null default now(),
  finished_at timestamptz,
  updated_at timestamptz not null default now()
);

create index corpus_parse_attempts_status_idx on public.corpus_parse_attempts(status, started_at desc);
create index corpus_parse_attempts_document_idx on public.corpus_parse_attempts(document_id) where document_id is not null;
create index corpus_parse_attempts_created_by_idx on public.corpus_parse_attempts(created_by) where created_by is not null;

alter table public.corpus_parse_attempts enable row level security;
revoke all on public.corpus_parse_attempts from anon, authenticated;
grant select, insert, update, delete on public.corpus_parse_attempts to service_role;

-- Applied to production as migration 20260816210012.
create table public.kpi_catalog (
  id text primary key,
  event_id text not null references public.deca_events(id) on delete cascade,
  code text not null,
  name text not null,
  cluster text not null default '',
  instructional_area text not null default '',
  standard text not null default '',
  source_updated_at timestamptz not null default now(),
  unique (event_id, code)
);

create table public.kpi_classification_batches (
  id uuid primary key default gen_random_uuid(),
  status text not null default 'queued'
    check (status in ('queued', 'processing', 'complete', 'failed')),
  requested_count integer not null check (requested_count between 1 and 100),
  processed_count integer not null default 0 check (processed_count >= 0),
  auto_approved_count integer not null default 0 check (auto_approved_count >= 0),
  needs_review_count integer not null default 0 check (needs_review_count >= 0),
  failed_count integer not null default 0 check (failed_count >= 0),
  created_by uuid references auth.users(id) on delete set null,
  created_at timestamptz not null default now(),
  started_at timestamptz,
  completed_at timestamptz
);

create table public.kpi_classifications (
  kpi_id text primary key references public.kpi_catalog(id) on delete cascade,
  skill_type text not null
    check (skill_type in ('concept', 'decision', 'communication', 'process', 'calculation_data', 'analysis')),
  complexity text not null check (complexity in ('quick', 'standard', 'deep')),
  primary_archetype text not null
    check (primary_archetype in ('concept_discovery', 'decision_lab', 'diagnose_problem', 'build_process', 'tradeoff_challenge', 'communication_coach', 'numbers_lab')),
  secondary_archetype text
    check (secondary_archetype is null or secondary_archetype in ('concept_discovery', 'decision_lab', 'diagnose_problem', 'build_process', 'tradeoff_challenge', 'communication_coach', 'numbers_lab')),
  learner_action text not null
    check (learner_action in ('identify', 'classify', 'predict', 'choose', 'rank', 'sequence', 'calculate', 'diagnose', 'compare', 'respond', 'justify')),
  deca_action text not null
    check (deca_action in ('explain', 'identify', 'demonstrate', 'analyze', 'calculate', 'recommend', 'justify', 'respond', 'develop', 'evaluate')),
  recommended_interactions jsonb not null default '[]'::jsonb,
  classification_reason text not null,
  certainty text not null check (certainty in ('high', 'medium', 'low')),
  ambiguity_reason text,
  alternative_archetype text,
  deterministic_check jsonb not null default '{}'::jsonb,
  reviewer_result jsonb not null default '{}'::jsonb,
  classifier_version text not null,
  classifier_model text not null,
  classification_schema_version integer not null default 1,
  classification_version integer not null default 1,
  review_status text not null
    check (review_status in ('auto_approved', 'needs_review', 'approved', 'blocked')),
  manual_override boolean not null default false,
  reviewed_by uuid references auth.users(id) on delete set null,
  reviewed_at timestamptz,
  review_deferred_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.kpi_classification_jobs (
  id uuid primary key default gen_random_uuid(),
  batch_id uuid not null references public.kpi_classification_batches(id) on delete cascade,
  kpi_id text not null references public.kpi_catalog(id) on delete cascade,
  status text not null default 'queued'
    check (status in ('queued', 'processing', 'auto_approved', 'needs_review', 'failed')),
  attempts integer not null default 0 check (attempts >= 0),
  failure_reason text,
  created_at timestamptz not null default now(),
  started_at timestamptz,
  completed_at timestamptz,
  unique (batch_id, kpi_id)
);

create index idx_kpi_classifications_review
  on public.kpi_classifications (review_status, updated_at);
create index idx_kpi_classification_jobs_batch_status
  on public.kpi_classification_jobs (batch_id, status);
create index idx_kpi_catalog_event
  on public.kpi_catalog (event_id, code);

alter table public.kpi_catalog enable row level security;
alter table public.kpi_classification_batches enable row level security;
alter table public.kpi_classifications enable row level security;
alter table public.kpi_classification_jobs enable row level security;

revoke all on table public.kpi_catalog from anon, authenticated;
revoke all on table public.kpi_classification_batches from anon, authenticated;
revoke all on table public.kpi_classifications from anon, authenticated;
revoke all on table public.kpi_classification_jobs from anon, authenticated;

grant select, insert, update, delete on table public.kpi_catalog to service_role;
grant select, insert, update, delete on table public.kpi_classification_batches to service_role;
grant select, insert, update, delete on table public.kpi_classifications to service_role;
grant select, insert, update, delete on table public.kpi_classification_jobs to service_role;

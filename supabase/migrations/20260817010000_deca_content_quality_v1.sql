-- DECA Content Quality Pipeline v1. Official curriculum remains immutable.

alter table public.kpi_knowledge_items drop constraint if exists kpi_knowledge_items_knowledge_type_check;
alter table public.kpi_knowledge_items add constraint kpi_knowledge_items_knowledge_type_check
  check (knowledge_type in ('definition','rule','formula','process','example','misconception','core_concept','mechanism','distinction','source_explanation'));
alter table public.kpi_knowledge_items add column if not exists pipeline_version text not null default 'deca-content-quality-2026-08-v1';
alter table public.kpi_knowledge_items add column if not exists authoritative boolean not null default false;

create table if not exists public.exam_item_quality_reviews (
  id uuid primary key default gen_random_uuid(),
  question_id uuid not null references public.kpi_questions(id) on delete cascade,
  kpi_code text not null,
  cognitive_demand text not null check (cognitive_demand in ('recall','comprehension','application','analysis','calculation')),
  choice_rationales jsonb not null check (jsonb_typeof(choice_rationales) = 'array' and jsonb_array_length(choice_rationales) = 4),
  source_claim_ids jsonb not null check (jsonb_typeof(source_claim_ids) = 'array' and jsonb_array_length(source_claim_ids) > 0),
  ambiguity_flags jsonb not null default '[]'::jsonb,
  style_metrics jsonb not null default '{}'::jsonb,
  review_status text not null default 'pending_review' check (review_status in ('pending_review','blocked','approved','rejected')),
  pipeline_version text not null default 'deca-content-quality-2026-08-v1',
  reviewed_by uuid references auth.users(id) on delete set null,
  reviewed_at timestamptz,
  created_at timestamptz not null default now(),
  unique(question_id)
);

create table if not exists public.roleplay_kpi_demonstrations (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  event_id text not null,
  session_id uuid,
  kpi_code text not null,
  demonstration_level smallint not null check (demonstration_level between 0 and 4),
  evidence text not null,
  feedback text not null,
  grader_version text not null default 'deca-content-quality-2026-08-v1',
  created_at timestamptz not null default now()
);

create index if not exists exam_item_quality_status_idx on public.exam_item_quality_reviews(review_status, cognitive_demand);
create index if not exists roleplay_demonstrations_user_event_idx on public.roleplay_kpi_demonstrations(user_id, event_id, created_at desc);

alter table public.exam_item_quality_reviews enable row level security;
alter table public.roleplay_kpi_demonstrations enable row level security;
revoke all on table public.exam_item_quality_reviews from anon, authenticated;
grant select, insert, update, delete on table public.exam_item_quality_reviews to service_role;
revoke all on table public.roleplay_kpi_demonstrations from anon, authenticated;
grant select, insert, update, delete on table public.roleplay_kpi_demonstrations to service_role;
grant select on table public.roleplay_kpi_demonstrations to authenticated;
create policy "Students read own roleplay demonstrations" on public.roleplay_kpi_demonstrations
  for select to authenticated using ((select auth.uid()) = user_id);

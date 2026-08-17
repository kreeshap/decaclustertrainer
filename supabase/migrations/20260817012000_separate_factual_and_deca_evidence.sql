alter table public.kpi_knowledge_items
  add column if not exists factual_evidence jsonb not null default '[]'::jsonb,
  add column if not exists deca_evidence jsonb not null default '[]'::jsonb,
  add column if not exists review_checklist jsonb not null default '{}'::jsonb,
  add column if not exists verification_class text not null default 'time_sensitive'
    check (verification_class in ('stable', 'time_sensitive')),
  add column if not exists reverify_after date;

comment on column public.kpi_knowledge_items.factual_evidence is
  'Current subject-appropriate authority supporting factual truth; separate from DECA alignment evidence.';
comment on column public.kpi_knowledge_items.deca_evidence is
  'Official DECA curriculum or sample material used only for competency alignment, relevance, or style.';

update public.kpi_knowledge_items
set deca_evidence = (
  select coalesce(jsonb_agg(jsonb_build_object(
    'source_type', 'official_deca_sample_exam',
    'purpose', 'alignment_or_style',
    'reference', value,
    'year', 2011
  )), '[]'::jsonb)
  from jsonb_array_elements_text(coalesce(source_references, '[]'::jsonb)) as refs(value)
)
where jsonb_array_length(deca_evidence) = 0
  and jsonb_array_length(coalesce(source_references, '[]'::jsonb)) > 0;

create or replace function public.enforce_kpi_knowledge_approval_evidence()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
begin
  if new.review_status = 'approved' then
    if new.authoritative is not true
       or new.reviewed_at is null
       or jsonb_typeof(new.factual_evidence) <> 'array'
       or jsonb_array_length(new.factual_evidence) = 0 then
      raise exception 'approved knowledge requires authoritative factual evidence and review metadata';
    end if;
    if not (
      coalesce((new.review_checklist->>'direct_support')::boolean, false)
      and coalesce((new.review_checklist->>'no_overclaim')::boolean, false)
      and coalesce((new.review_checklist->>'subject_authority')::boolean, false)
      and coalesce((new.review_checklist->>'current')::boolean, false)
      and coalesce((new.review_checklist->>'atomic')::boolean, false)
      and coalesce((new.review_checklist->>'deca_connection')::boolean, false)
    ) then
      raise exception 'all knowledge approval checklist items must be confirmed';
    end if;
    if new.verification_class = 'time_sensitive' and new.reverify_after is null then
      raise exception 'time-sensitive knowledge requires reverify_after';
    end if;
  end if;
  return new;
end;
$$;

drop trigger if exists enforce_kpi_knowledge_approval_evidence_trigger
  on public.kpi_knowledge_items;
create trigger enforce_kpi_knowledge_approval_evidence_trigger
before insert or update on public.kpi_knowledge_items
for each row execute function public.enforce_kpi_knowledge_approval_evidence();

revoke execute on function public.enforce_kpi_knowledge_approval_evidence() from public, anon, authenticated;
grant execute on function public.enforce_kpi_knowledge_approval_evidence() to service_role;

create index if not exists kpi_knowledge_reverify_after_idx
  on public.kpi_knowledge_items (reverify_after)
  where review_status = 'approved' and reverify_after is not null;

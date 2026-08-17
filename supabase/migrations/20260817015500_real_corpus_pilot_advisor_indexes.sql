create index if not exists corpus_parser_failures_resolved_by_idx
  on public.corpus_parser_failures(resolved_by) where resolved_by is not null;
create index if not exists corpus_style_profiles_previous_idx
  on public.corpus_style_profile_snapshots(previous_snapshot_id) where previous_snapshot_id is not null;

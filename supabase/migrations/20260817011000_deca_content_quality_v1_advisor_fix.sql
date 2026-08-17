-- Cover the reviewer foreign key reported by the Supabase performance advisor.
create index if not exists exam_item_quality_reviews_reviewed_by_idx
  on public.exam_item_quality_reviews (reviewed_by)
  where reviewed_by is not null;

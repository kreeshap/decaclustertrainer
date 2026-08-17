create index if not exists practice_corpus_duplicate_of_idx on public.practice_corpus_documents(duplicate_of) where duplicate_of is not null;
create index if not exists practice_corpus_created_by_idx on public.practice_corpus_documents(created_by) where created_by is not null;
create index if not exists practice_corpus_verified_by_idx on public.practice_corpus_documents(verified_by) where verified_by is not null;
create index if not exists reference_exam_duplicate_of_idx on public.reference_exam_questions(duplicate_of) where duplicate_of is not null;
create index if not exists reference_exam_verified_by_idx on public.reference_exam_questions(verified_by) where verified_by is not null;
create index if not exists reference_roleplay_verified_by_idx on public.reference_roleplays(verified_by) where verified_by is not null;

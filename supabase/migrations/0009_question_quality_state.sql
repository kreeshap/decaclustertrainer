-- 0009_question_quality_state.sql
-- Add generated quality metadata for MCQs and answer reveal state.

ALTER TABLE kpi_questions
  ADD COLUMN IF NOT EXISTS quality_state JSONB NOT NULL DEFAULT '{}'::jsonb,
  ADD COLUMN IF NOT EXISTS answer_reveal JSONB NOT NULL DEFAULT '{}'::jsonb;

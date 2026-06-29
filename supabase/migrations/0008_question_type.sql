-- 0008_question_type.sql
-- Add question_type column to kpi_questions.
-- Existing rows default to 'recognition' (backward compatible).

ALTER TABLE kpi_questions
  ADD COLUMN IF NOT EXISTS question_type TEXT NOT NULL DEFAULT 'recognition'
    CHECK (question_type IN ('recognition', 'application'));

CREATE INDEX IF NOT EXISTS idx_kpi_questions_type
  ON kpi_questions (kpi_code, question_type);

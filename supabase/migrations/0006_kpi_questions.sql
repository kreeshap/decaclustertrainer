-- ─────────────────────────────────────────────────────────────────────────────
-- 0006_kpi_questions.sql
-- Stores AI-generated KPI questions and per-user answer history.
-- ─────────────────────────────────────────────────────────────────────────────

-- ── kpi_questions ─────────────────────────────────────────────────────────────
-- One row per generated question. Seeded by the backend after Groq generation.
-- Never written by the client directly.

CREATE TABLE IF NOT EXISTS kpi_questions (
  id             UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  kpi_code       TEXT        NOT NULL,               -- e.g. "BL:163"
  kpi_text       TEXT        NOT NULL DEFAULT '',    -- full indicator text
  kpi_cluster    TEXT        NOT NULL DEFAULT '',    -- subject cluster, e.g. "Business Law (BL)"
  deca_cluster   TEXT        NOT NULL DEFAULT '',    -- career cluster,  e.g. "Finance"
  event_id       TEXT        NOT NULL DEFAULT '',    -- e.g. "financial_services_tdm"
  question_text  TEXT        NOT NULL,
  choices        JSONB       NOT NULL DEFAULT '[]',  -- ["Choice A", …, "Choice D"]
  correct_index  INTEGER     NOT NULL DEFAULT 0
                   CHECK (correct_index BETWEEN 0 AND 3),
  explanation    TEXT        NOT NULL DEFAULT '',    -- why correct is right + why others are wrong
  created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_kpi_questions_kpi_code
  ON kpi_questions (kpi_code);

CREATE INDEX IF NOT EXISTS idx_kpi_questions_event_id
  ON kpi_questions (event_id);

CREATE INDEX IF NOT EXISTS idx_kpi_questions_deca_cluster
  ON kpi_questions (deca_cluster);

-- ── user_question_results ─────────────────────────────────────────────────────
-- One row per (user, question) pair — upserted each time the user answers.
-- Tracks whether the most recent attempt was correct.

CREATE TABLE IF NOT EXISTS user_question_results (
  id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id      UUID        NOT NULL,
  question_id  UUID        NOT NULL REFERENCES kpi_questions(id) ON DELETE CASCADE,
  correct      BOOLEAN     NOT NULL DEFAULT FALSE,
  answered_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (user_id, question_id)
);

CREATE INDEX IF NOT EXISTS idx_uqr_user_id
  ON user_question_results (user_id);

CREATE INDEX IF NOT EXISTS idx_uqr_user_question
  ON user_question_results (user_id, question_id);

-- ── Row-level security ────────────────────────────────────────────────────────

ALTER TABLE kpi_questions          ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_question_results  ENABLE ROW LEVEL SECURITY;

-- All authenticated users can read questions.
-- Only the service role (backend) can INSERT (no client-side insert policy).
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE tablename = 'kpi_questions' AND policyname = 'kpi_questions_select'
  ) THEN
    CREATE POLICY kpi_questions_select ON kpi_questions
      FOR SELECT TO authenticated USING (true);
  END IF;
END $$;

-- Users can read, insert, and update their own answer rows.
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE tablename = 'user_question_results' AND policyname = 'uqr_select_own'
  ) THEN
    CREATE POLICY uqr_select_own ON user_question_results
      FOR SELECT TO authenticated USING (auth.uid() = user_id);
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE tablename = 'user_question_results' AND policyname = 'uqr_insert_own'
  ) THEN
    CREATE POLICY uqr_insert_own ON user_question_results
      FOR INSERT TO authenticated WITH CHECK (auth.uid() = user_id);
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE tablename = 'user_question_results' AND policyname = 'uqr_update_own'
  ) THEN
    CREATE POLICY uqr_update_own ON user_question_results
      FOR UPDATE TO authenticated USING (auth.uid() = user_id);
  END IF;
END $$;

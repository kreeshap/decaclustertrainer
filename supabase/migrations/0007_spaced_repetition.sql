-- ─────────────────────────────────────────────────────────────────────────────
-- 0007_spaced_repetition.sql
-- Full spaced-repetition + mastery-tracking schema.
-- ─────────────────────────────────────────────────────────────────────────────

-- ── 1. SRS state — one row per (user, question) ───────────────────────────────
-- Stores SM-2 state so each question is scheduled independently.

CREATE TABLE IF NOT EXISTS user_srs_state (
  id              UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id         UUID          NOT NULL,
  question_id     UUID          NOT NULL REFERENCES kpi_questions(id) ON DELETE CASCADE,

  -- SM-2 core fields
  ease_factor     NUMERIC(4,2)  NOT NULL DEFAULT 2.50,   -- ≥ 1.3
  interval_days   INTEGER       NOT NULL DEFAULT 0,
  repetitions     INTEGER       NOT NULL DEFAULT 0,
  last_quality    SMALLINT      CHECK (last_quality BETWEEN 0 AND 5),

  -- Scheduling
  last_reviewed   TIMESTAMPTZ,
  next_review     TIMESTAMPTZ   NOT NULL DEFAULT NOW(),

  -- Lifetime stats
  total_attempts  INTEGER       NOT NULL DEFAULT 0,
  correct_attempts INTEGER      NOT NULL DEFAULT 0,

  UNIQUE (user_id, question_id)
);

CREATE INDEX IF NOT EXISTS idx_srs_user           ON user_srs_state (user_id);
CREATE INDEX IF NOT EXISTS idx_srs_next_review    ON user_srs_state (user_id, next_review);
CREATE INDEX IF NOT EXISTS idx_srs_question       ON user_srs_state (question_id);

-- ── 2. KPI mastery — one row per (user, kpi_code) ────────────────────────────
-- Aggregated mastery score computed after each answer session.

CREATE TABLE IF NOT EXISTS user_kpi_mastery (
  id                   UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id              UUID          NOT NULL,
  kpi_code             TEXT          NOT NULL,
  kpi_cluster          TEXT          NOT NULL DEFAULT '',
  deca_cluster         TEXT          NOT NULL DEFAULT '',
  event_id             TEXT          NOT NULL DEFAULT '',

  -- Mastery 0–100 (recomputed on every answer for this KPI)
  mastery_score        NUMERIC(5,2)  NOT NULL DEFAULT 0,

  -- Coverage
  questions_seen       INTEGER       NOT NULL DEFAULT 0,
  questions_mastered   INTEGER       NOT NULL DEFAULT 0,  -- interval_days ≥ 7
  total_questions      INTEGER       NOT NULL DEFAULT 0,  -- known from kpi_questions

  -- Scheduling
  last_studied         TIMESTAMPTZ,
  next_review          TIMESTAMPTZ,

  UNIQUE (user_id, kpi_code)
);

CREATE INDEX IF NOT EXISTS idx_kpim_user          ON user_kpi_mastery (user_id);
CREATE INDEX IF NOT EXISTS idx_kpim_event         ON user_kpi_mastery (user_id, event_id);
CREATE INDEX IF NOT EXISTS idx_kpim_mastery       ON user_kpi_mastery (user_id, mastery_score);

-- ── 3. Study sessions ─────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS user_study_sessions (
  id                   UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id              UUID          NOT NULL,
  event_id             TEXT          NOT NULL DEFAULT '',
  session_type         TEXT          NOT NULL DEFAULT 'full', -- 'full' | 'review'

  started_at           TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
  ended_at             TIMESTAMPTZ,
  duration_seconds     INTEGER,

  -- Aggregates (written on session end)
  kpis_studied         INTEGER       NOT NULL DEFAULT 0,
  questions_answered   INTEGER       NOT NULL DEFAULT 0,
  questions_correct    INTEGER       NOT NULL DEFAULT 0,
  vocab_total          INTEGER       NOT NULL DEFAULT 0,
  vocab_correct        INTEGER       NOT NULL DEFAULT 0,
  roleplay_score       SMALLINT,     -- NULL if no roleplay this session
  accuracy_pct         NUMERIC(5,2)  -- questions_correct / questions_answered * 100
);

CREATE INDEX IF NOT EXISTS idx_sess_user          ON user_study_sessions (user_id);
CREATE INDEX IF NOT EXISTS idx_sess_started       ON user_study_sessions (user_id, started_at DESC);

-- ── 4. Daily activity — for streak + heatmap ──────────────────────────────────

CREATE TABLE IF NOT EXISTS user_daily_activity (
  id                   UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id              UUID    NOT NULL,
  activity_date        DATE    NOT NULL DEFAULT CURRENT_DATE,

  questions_answered   INTEGER NOT NULL DEFAULT 0,
  questions_correct    INTEGER NOT NULL DEFAULT 0,
  kpis_studied         INTEGER NOT NULL DEFAULT 0,
  minutes_studied      INTEGER NOT NULL DEFAULT 0,

  UNIQUE (user_id, activity_date)
);

CREATE INDEX IF NOT EXISTS idx_daily_user         ON user_daily_activity (user_id);
CREATE INDEX IF NOT EXISTS idx_daily_date         ON user_daily_activity (user_id, activity_date DESC);

-- ── RLS ───────────────────────────────────────────────────────────────────────

ALTER TABLE user_srs_state       ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_kpi_mastery     ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_study_sessions  ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_daily_activity  ENABLE ROW LEVEL SECURITY;

DO $$
DECLARE tbl TEXT;
BEGIN
  FOREACH tbl IN ARRAY ARRAY[
    'user_srs_state', 'user_kpi_mastery',
    'user_study_sessions', 'user_daily_activity'
  ] LOOP
    -- SELECT
    IF NOT EXISTS (
      SELECT 1 FROM pg_policies WHERE tablename = tbl AND policyname = tbl || '_select'
    ) THEN
      EXECUTE format(
        'CREATE POLICY %I ON %I FOR SELECT TO authenticated USING (auth.uid() = user_id)',
        tbl || '_select', tbl
      );
    END IF;
    -- INSERT
    IF NOT EXISTS (
      SELECT 1 FROM pg_policies WHERE tablename = tbl AND policyname = tbl || '_insert'
    ) THEN
      EXECUTE format(
        'CREATE POLICY %I ON %I FOR INSERT TO authenticated WITH CHECK (auth.uid() = user_id)',
        tbl || '_insert', tbl
      );
    END IF;
    -- UPDATE
    IF NOT EXISTS (
      SELECT 1 FROM pg_policies WHERE tablename = tbl AND policyname = tbl || '_update'
    ) THEN
      EXECUTE format(
        'CREATE POLICY %I ON %I FOR UPDATE TO authenticated USING (auth.uid() = user_id)',
        tbl || '_update', tbl
      );
    END IF;
  END LOOP;
END $$;

-- ── Helper view — "due questions for a user" ──────────────────────────────────
-- Returns question ids where next_review <= now(), joined with kpi metadata.

CREATE OR REPLACE VIEW v_due_questions AS
SELECT
  s.user_id,
  s.question_id,
  s.ease_factor,
  s.interval_days,
  s.repetitions,
  s.next_review,
  s.total_attempts,
  s.correct_attempts,
  q.kpi_code,
  q.kpi_text,
  q.kpi_cluster,
  q.deca_cluster,
  q.event_id,
  q.question_text,
  q.choices,
  q.correct_index,
  q.explanation
FROM user_srs_state s
JOIN kpi_questions  q ON q.id = s.question_id
WHERE s.next_review <= NOW();

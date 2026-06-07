-- Add user preference columns to public.profiles.
-- Existing owner RLS policies (select / update / insert) already cover these columns.

ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS avatar_url text;
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS competition_tier text NOT NULL DEFAULT 'districts';
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS default_cluster text NOT NULL DEFAULT '';
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS session_time_pref text NOT NULL DEFAULT 'morning';
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS randomize_clusters boolean NOT NULL DEFAULT false;
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS theme text NOT NULL DEFAULT 'dark';
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS study_goal_minutes integer NOT NULL DEFAULT 30;
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS study_goal_kpis integer NOT NULL DEFAULT 5;
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS notif_session_reminders boolean NOT NULL DEFAULT true;
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS notif_weekly_progress boolean NOT NULL DEFAULT true;
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS notif_admin_announcements boolean NOT NULL DEFAULT false;
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS notif_competition_countdown boolean NOT NULL DEFAULT true;
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS privacy_track_progress boolean NOT NULL DEFAULT true;

-- Add preferred event column to profiles.
-- default_cluster already exists from 0002.
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS default_event text NOT NULL DEFAULT '';

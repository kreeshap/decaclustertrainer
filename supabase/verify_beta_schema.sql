-- Run after migrations. Success returns zero rows; every returned row is drift.
with required(table_name,column_name) as (values
 ('profiles','default_event_id'),('profiles','competition_tier'),('profiles','default_cluster'),
 ('deca_events','id'),('deca_events','name'),('kpi_questions','event_id'),('kpi_questions','question_slot'),
 ('responses','user_id'),('responses','event_id'),('responses','session_id'),('responses','question_id'),('responses','selected_index'),
 ('user_srs_state','event_id'),('user_srs_state','question_id'),('user_kpi_mastery','event_id'),('user_kpi_mastery','kpi_code'),
 ('user_study_sessions','event_id'),('user_study_sessions','ar_answers'),('user_study_sessions','roleplay_result'),('user_daily_activity','event_id'),
 ('user_adaptive_state','user_id'),('user_adaptive_state','event_id'),('user_adaptive_state','state'),
 ('user_today_plans','user_id'),('user_today_plans','event_id'),('user_today_plans','plan_date'),('user_today_plans','tasks'),
 ('kpi_inference_state','event_id'),('user_timing_profile','event_id'),('learning_evaluation_log','event_id'),
 ('system_announcements','title')
), missing_columns as (
 select 'missing column'::text as problem, r.table_name||'.'||r.column_name as object
 from required r left join information_schema.columns c
   on c.table_schema='public' and c.table_name=r.table_name and c.column_name=r.column_name
 where c.column_name is null
), missing_rls as (
 select 'RLS disabled', r.table_name from (select distinct table_name from required) r
 left join pg_class c on c.relname=r.table_name
 left join pg_namespace n on n.oid=c.relnamespace and n.nspname='public'
 where c.oid is null or not c.relrowsecurity
), missing_view as (
 select 'missing view','v_due_questions' where to_regclass('public.v_due_questions') is null
), missing_function as (
 select 'missing function','handle_new_auth_user' where to_regprocedure('public.handle_new_auth_user()') is null
 union all select 'missing function','record_beta_answer'
 where to_regprocedure('public.record_beta_answer(uuid,uuid,integer,integer,integer,integer,text)') is null
 union all select 'missing function','finish_beta_session'
 where to_regprocedure('public.finish_beta_session(uuid,integer,integer,integer,integer,integer,jsonb)') is null
), missing_event as (
 select 'missing beta event',e.id from (values ('accounting_application_series'),('business_finance_series'),('financial_services_tdm')) e(id)
 left join public.deca_events d on d.id=e.id and d.is_beta where d.id is null
)
select * from missing_columns union all select * from missing_rls union all select * from missing_view
union all select * from missing_function union all select * from missing_event;

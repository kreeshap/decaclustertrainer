-- Phase 3: atomic answer and session-completion transactions.

do $$ begin
  if not exists (select 1 from pg_constraint where conname='responses_selected_index_check' and conrelid='public.responses'::regclass) then
    alter table public.responses add constraint responses_selected_index_check
      check(selected_index between 0 and 3) not valid;
  end if;
  if not exists (select 1 from pg_constraint where conname='responses_selected_index_required' and conrelid='public.responses'::regclass) then
    -- NOT VALID preserves any legacy null row but rejects nulls from every new write.
    alter table public.responses add constraint responses_selected_index_required
      check(selected_index is not null) not valid;
  end if;
  if not exists (select 1 from pg_constraint where conname='kpi_questions_choice_shape_check' and conrelid='public.kpi_questions'::regclass) then
    alter table public.kpi_questions add constraint kpi_questions_choice_shape_check
      check(jsonb_typeof(choices)='array' and jsonb_array_length(choices)=4) not valid;
  end if;
  if not exists (select 1 from pg_constraint where conname='kpi_questions_beta_type_slot_check' and conrelid='public.kpi_questions'::regclass) then
    alter table public.kpi_questions add constraint kpi_questions_beta_type_slot_check
      check((question_type='recognition' and question_slot between 0 and 4)
         or (question_type='application' and question_slot=0)) not valid;
  end if;
  if not exists (select 1 from pg_constraint where conname='user_study_sessions_roleplay_score_check' and conrelid='public.user_study_sessions'::regclass) then
    alter table public.user_study_sessions add constraint user_study_sessions_roleplay_score_check
      check(roleplay_score between 1 and 10) not valid;
  end if;
end $$;
alter table public.user_study_sessions add column if not exists roleplay_result jsonb not null default '{}'::jsonb;

create or replace function public.record_beta_answer(
  p_session_id uuid,
  p_question_id uuid,
  p_selected_index integer,
  p_response_time_ms integer,
  p_time_to_first_ms integer,
  p_answer_change_count integer,
  p_idempotency_key text
) returns jsonb
language plpgsql
security invoker
set search_path = public
as $$
declare
  v_user uuid := auth.uid();
  v_question public.kpi_questions%rowtype;
  v_session public.user_study_sessions%rowtype;
  v_existing public.responses%rowtype;
  v_correct boolean;
  v_now timestamptz := now();
  v_ef numeric := 2.50;
  v_interval integer := 0;
  v_repetitions integer := 0;
  v_total_attempts integer := 0;
  v_correct_attempts integer := 0;
  v_quality integer;
  v_new_ef numeric;
  v_new_interval integer;
  v_new_repetitions integer;
  v_next_review timestamptz;
  v_baseline integer := 12000;
  v_baseline_count integer := 0;
  v_new_baseline integer;
  v_instant numeric;
  v_prev_mastery numeric := .5;
  v_prev_recognition numeric := .5;
  v_prev_application numeric := .5;
  v_prev_confidence numeric := .5;
  v_inference_samples integer := 0;
  v_new_mastery numeric;
  v_new_recognition numeric;
  v_new_application numeric;
  v_new_confidence numeric;
  v_uncertainty numeric;
  v_attempts integer;
  v_correct_count integer;
  v_seen integer;
  v_mastered integer;
  v_question_count integer;
  v_mastery_score numeric;
  v_response_id uuid;
begin
  if v_user is null then raise exception 'authentication required' using errcode='28000'; end if;
  if p_selected_index not between 0 and 3 then raise exception 'selected answer is invalid' using errcode='22023'; end if;
  if p_response_time_ms < 0 or coalesce(p_answer_change_count,0) < 0
     or (p_time_to_first_ms is not null and (p_time_to_first_ms < 0 or p_time_to_first_ms > p_response_time_ms))
     or length(trim(coalesce(p_idempotency_key,''))) < 8 then
    raise exception 'invalid answer telemetry' using errcode='22023';
  end if;

  perform pg_advisory_xact_lock(hashtextextended(p_idempotency_key,0));
  select * into v_existing from public.responses
  where user_id=v_user and idempotency_hash=p_idempotency_key;
  if found then
    return jsonb_build_object('ok',true,'duplicate',true,'response_id',v_existing.id,'correct',v_existing.correct);
  end if;

  select * into strict v_session from public.user_study_sessions
  where id=p_session_id and user_id=v_user for update;
  if v_session.ended_at is not null then raise exception 'study session is already complete' using errcode='22023'; end if;
  select * into strict v_question from public.kpi_questions
  where id=p_question_id and event_id=v_session.event_id;
  v_correct := p_selected_index=v_question.correct_index;

  select ease_factor,interval_days,repetitions,total_attempts,correct_attempts
  into v_ef,v_interval,v_repetitions,v_total_attempts,v_correct_attempts
  from public.user_srs_state
  where user_id=v_user and event_id=v_question.event_id and question_id=v_question.id for update;
  if not found then
    v_ef:=2.50; v_interval:=0; v_repetitions:=0; v_total_attempts:=0; v_correct_attempts:=0;
  end if;

  select median_ms,sample_count into v_baseline,v_baseline_count
  from public.user_timing_profile
  where user_id=v_user and event_id=v_question.event_id
    and question_type=v_question.question_type and kpi_cluster=v_question.kpi_cluster for update;
  if not found then v_baseline:=12000; v_baseline_count:=0; end if;

  select mastery_prob,recognition_mastery,application_mastery,confidence_est,sample_count
  into v_prev_mastery,v_prev_recognition,v_prev_application,v_prev_confidence,v_inference_samples
  from public.kpi_inference_state
  where user_id=v_user and event_id=v_question.event_id and kpi_code=v_question.kpi_code for update;
  if not found then
    v_prev_mastery:=.5; v_prev_recognition:=.5; v_prev_application:=.5; v_prev_confidence:=.5; v_inference_samples:=0;
  end if;

  v_quality := case when v_correct then 4 else 1 end;
  if v_quality < 3 then v_new_repetitions:=0; v_new_interval:=1;
  else
    v_new_interval := case when v_repetitions=0 then 1 when v_repetitions=1 then 6 else greatest(1,round(v_interval*v_ef)::integer) end;
    v_new_repetitions := v_repetitions+1;
  end if;
  v_new_ef := greatest(1.30,round((v_ef + .1-(5-v_quality)*(.08+(5-v_quality)*.02))::numeric,2));
  v_next_review := v_now + make_interval(days=>v_new_interval);
  v_instant := case when v_correct
    then greatest(.55,least(.98,1-(p_response_time_ms::numeric/greatest(v_baseline,1))*.25))
    else greatest(.05,least(.45,(p_response_time_ms::numeric/greatest(v_baseline,1))*.15)) end;
  v_new_baseline := round((v_baseline*v_baseline_count+p_response_time_ms)::numeric/(v_baseline_count+1));
  v_new_confidence := round(((v_prev_confidence*least(v_inference_samples,9)+v_instant)/(least(v_inference_samples,9)+1))::numeric,5);
  v_new_mastery := greatest(0,least(1,v_prev_mastery + case when v_correct then .10 else -.14 end));
  v_new_recognition := case when v_question.question_type='recognition' then greatest(0,least(1,v_prev_recognition+case when v_correct then .12 else -.15 end)) else v_prev_recognition end;
  v_new_application := case when v_question.question_type='application' then greatest(0,least(1,v_prev_application+case when v_correct then .12 else -.15 end)) else v_prev_application end;
  v_uncertainty := round((1-abs(v_new_mastery-.5)*2)::numeric,5);

  insert into public.responses(user_id,event_id,session_id,question_id,kpi_code,question_type,selected_index,correct,
    response_time_ms,time_to_first_ms,answer_changed,answer_change_count,instant_confidence,is_valid,idempotency_hash,answered_at)
  values(v_user,v_question.event_id,v_session.id,v_question.id,v_question.kpi_code,v_question.question_type,p_selected_index,v_correct,
    p_response_time_ms,p_time_to_first_ms,coalesce(p_answer_change_count,0)>0,coalesce(p_answer_change_count,0),v_instant,true,p_idempotency_key,v_now)
  returning id into v_response_id;

  insert into public.user_srs_state(user_id,event_id,question_id,ease_factor,interval_days,repetitions,last_quality,last_reviewed,next_review,total_attempts,correct_attempts)
  values(v_user,v_question.event_id,v_question.id,v_new_ef,v_new_interval,v_new_repetitions,v_quality,v_now,v_next_review,v_total_attempts+1,v_correct_attempts+case when v_correct then 1 else 0 end)
  on conflict(user_id,event_id,question_id) do update set ease_factor=excluded.ease_factor,interval_days=excluded.interval_days,
    repetitions=excluded.repetitions,last_quality=excluded.last_quality,last_reviewed=excluded.last_reviewed,next_review=excluded.next_review,
    total_attempts=excluded.total_attempts,correct_attempts=excluded.correct_attempts;

  insert into public.kpi_inference_state(user_id,event_id,kpi_code,mastery_prob,recognition_mastery,application_mastery,confidence_est,last_instant_confidence,uncertainty,sample_count,last_updated)
  values(v_user,v_question.event_id,v_question.kpi_code,v_new_mastery,v_new_recognition,v_new_application,v_new_confidence,v_instant,v_uncertainty,v_inference_samples+1,v_now)
  on conflict(user_id,event_id,kpi_code) do update set mastery_prob=excluded.mastery_prob,recognition_mastery=excluded.recognition_mastery,
    application_mastery=excluded.application_mastery,confidence_est=excluded.confidence_est,last_instant_confidence=excluded.last_instant_confidence,
    uncertainty=excluded.uncertainty,sample_count=excluded.sample_count,last_updated=excluded.last_updated;

  insert into public.user_timing_profile(user_id,event_id,question_type,kpi_cluster,median_ms,sample_count,updated_at)
  values(v_user,v_question.event_id,v_question.question_type,v_question.kpi_cluster,v_new_baseline,v_baseline_count+1,v_now)
  on conflict(user_id,event_id,question_type,kpi_cluster) do update set median_ms=excluded.median_ms,sample_count=excluded.sample_count,updated_at=excluded.updated_at;

  select count(*),count(*) filter(where correct),count(distinct question_id) into v_attempts,v_correct_count,v_seen
  from public.responses where user_id=v_user and event_id=v_question.event_id and kpi_code=v_question.kpi_code and is_valid;
  select count(*) into v_mastered from public.user_srs_state s join public.kpi_questions q on(q.id=s.question_id and q.event_id=s.event_id)
  where s.user_id=v_user and s.event_id=v_question.event_id and q.kpi_code=v_question.kpi_code and s.interval_days>=7;
  select count(*) into v_question_count from public.kpi_questions where event_id=v_question.event_id and kpi_code=v_question.kpi_code;
  v_mastery_score := round((70*(v_correct_count::numeric/greatest(v_attempts,1))+30*(v_seen::numeric/greatest(v_question_count,1)))::numeric,2);
  insert into public.user_kpi_mastery(user_id,event_id,kpi_code,kpi_cluster,deca_cluster,mastery_score,questions_seen,questions_mastered,total_questions,last_studied,next_review)
  select v_user,v_question.event_id,v_question.kpi_code,v_question.kpi_cluster,v_question.deca_cluster,v_mastery_score,v_seen,v_mastered,v_question_count,v_now,
    min(s.next_review) from public.user_srs_state s join public.kpi_questions q on(q.id=s.question_id and q.event_id=s.event_id)
    where s.user_id=v_user and s.event_id=v_question.event_id and q.kpi_code=v_question.kpi_code
  on conflict(user_id,event_id,kpi_code) do update set mastery_score=excluded.mastery_score,questions_seen=excluded.questions_seen,
    questions_mastered=excluded.questions_mastered,total_questions=excluded.total_questions,last_studied=excluded.last_studied,next_review=excluded.next_review;

  insert into public.learning_evaluation_log(user_id,event_id,kpi_code,kpi_cluster,question_type,recognition_mastery,application_mastery,predicted_mastery,
    confidence_est,instant_confidence,volatility,uncertainty,correct,response_time_ms,recorded_at)
  values(v_user,v_question.event_id,v_question.kpi_code,v_question.kpi_cluster,v_question.question_type,v_new_recognition,v_new_application,v_prev_mastery,
    v_new_confidence,v_instant,abs(v_instant-v_new_confidence),v_uncertainty,v_correct,p_response_time_ms,v_now);

  insert into public.user_daily_activity(user_id,event_id,activity_date,questions_answered,questions_correct)
  values(v_user,v_question.event_id,current_date,1,case when v_correct then 1 else 0 end)
  on conflict(user_id,event_id,activity_date) do update set questions_answered=public.user_daily_activity.questions_answered+1,
    questions_correct=public.user_daily_activity.questions_correct+case when v_correct then 1 else 0 end;
  update public.user_study_sessions set questions_answered=questions_answered+1,
    questions_correct=questions_correct+case when v_correct then 1 else 0 end where id=v_session.id and user_id=v_user;

  return jsonb_build_object('ok',true,'duplicate',false,'response_id',v_response_id,'correct',v_correct,'next_review',v_next_review,
    'mastery_score',v_mastery_score,'srs',jsonb_build_object('ease_factor',v_new_ef,'interval_days',v_new_interval,'repetitions',v_new_repetitions));
exception when no_data_found then
  raise exception 'question or session not found for authenticated user' using errcode='P0002';
end;
$$;

create or replace function public.finish_beta_session(
  p_session_id uuid,
  p_duration_seconds integer,
  p_kpis_studied integer,
  p_vocab_total integer,
  p_vocab_correct integer,
  p_roleplay_score integer,
  p_ar_answers jsonb
) returns jsonb
language plpgsql
security invoker
set search_path=public
as $$
declare v_user uuid:=auth.uid(); v_session public.user_study_sessions%rowtype; v_accuracy numeric; v_kpis_studied integer;
begin
  if v_user is null then raise exception 'authentication required' using errcode='28000'; end if;
  select * into strict v_session from public.user_study_sessions where id=p_session_id and user_id=v_user for update;
  if v_session.ended_at is not null then
    return jsonb_build_object('ok',true,'duplicate',true,'accuracy_pct',v_session.accuracy_pct,
      'questions_answered',v_session.questions_answered,'questions_correct',v_session.questions_correct);
  end if;
  if p_roleplay_score is not null and p_roleplay_score not between 1 and 10 then
    raise exception 'invalid roleplay score' using errcode='22023';
  end if;
  if p_ar_answers is not null and jsonb_typeof(p_ar_answers) <> 'array' then
    raise exception 'active recall answers must be an array' using errcode='22023';
  end if;
  select count(distinct kpi_code) into v_kpis_studied
  from public.responses where user_id=v_user and session_id=p_session_id and is_valid;
  v_accuracy:=round((100*v_session.questions_correct::numeric/greatest(v_session.questions_answered,1))::numeric,2);
  update public.user_study_sessions set ended_at=now(),duration_seconds=greatest(p_duration_seconds,0),kpis_studied=v_kpis_studied,
    vocab_total=greatest(p_vocab_total,0),vocab_correct=least(greatest(p_vocab_correct,0),greatest(p_vocab_total,0)),
    accuracy_pct=v_accuracy,ar_answers=coalesce(p_ar_answers,'[]'::jsonb) where id=p_session_id and user_id=v_user;
  insert into public.user_daily_activity(user_id,event_id,activity_date,kpis_studied,minutes_studied)
  values(v_user,v_session.event_id,current_date,v_kpis_studied,greatest(p_duration_seconds,0)/60)
  on conflict(user_id,event_id,activity_date) do update set kpis_studied=public.user_daily_activity.kpis_studied+excluded.kpis_studied,
    minutes_studied=public.user_daily_activity.minutes_studied+excluded.minutes_studied;
  return jsonb_build_object('ok',true,'accuracy_pct',v_accuracy,'kpis_studied',v_kpis_studied,
    'questions_answered',v_session.questions_answered,'questions_correct',v_session.questions_correct);
exception when no_data_found then raise exception 'study session not found' using errcode='P0002';
end;
$$;

revoke all on function public.record_beta_answer(uuid,uuid,integer,integer,integer,integer,text) from public,anon;
revoke all on function public.finish_beta_session(uuid,integer,integer,integer,integer,integer,jsonb) from public,anon;
grant execute on function public.record_beta_answer(uuid,uuid,integer,integer,integer,integer,text) to authenticated;
grant execute on function public.finish_beta_session(uuid,integer,integer,integer,integer,integer,jsonb) to authenticated;

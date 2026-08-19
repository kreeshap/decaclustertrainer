"""Persistent Practice Platform: selection, resumability, flags, and analysis."""

from collections import defaultdict
from datetime import datetime, timezone
import random

from flask import Blueprint, jsonify, request

from ..auth_utils import get_current_user
from ..events import canonical_event_id
from ..learn_helpers import _load_all_kpis, _supabase_svc
from ..student_evidence import first_attempts, topic_is_qualified

practice_bp = Blueprint("practice_platform", __name__)


def now(): return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def require_user():
    user = get_current_user()
    return (user, None) if user else (None, (jsonify({"error": "Unauthorized"}), 401))


def _data(user_id: str, event_id: str):
    _, questions = _supabase_svc("/kpi_questions", params={"event_id": f"eq.{event_id}", "review_status": "eq.approved", "select": "id,kpi_code,kpi_text,kpi_cluster,deca_cluster,question_text,choices,correct_index,explanation,question_type,designed_difficulty,empirical_difficulty,source_type", "limit": "10000"})
    _, responses = _supabase_svc("/responses", params={"user_id": f"eq.{user_id}", "event_id": f"eq.{event_id}", "select": "question_id,kpi_code,correct,answered_at,response_time_ms", "order": "answered_at.asc", "limit": "20000"})
    _, flags = _supabase_svc("/question_flags", params={"user_id": f"eq.{user_id}", "event_id": f"eq.{event_id}", "select": "question_id", "limit": "10000"})
    _, due = _supabase_svc("/user_srs_state", params={"user_id": f"eq.{user_id}", "event_id": f"eq.{event_id}", "next_review": f"lte.{now()}", "select": "question_id", "limit": "10000"})
    return questions or [], responses or [], {r["question_id"] for r in flags or []}, {r["question_id"] for r in due or []}


def _analytics(questions, responses, catalog, mastery):
    qmap = {q["id"]: q for q in questions}; topics = defaultdict(lambda: {"correct": 0, "attempts": 0, "kpis": defaultdict(lambda: [0, 0])})
    for row in catalog:
        topic = row.get("cluster") or "Other"
        if row.get("code"): topics[topic].setdefault("total_kpis", set()).add(row["code"])
    for row in mastery:
        topic = row.get("kpi_cluster") or row.get("deca_cluster") or "Other"
        if row.get("kpi_code"): topics[topic].setdefault("studied_kpis", set()).add(row["kpi_code"])
    evidence = first_attempts(responses)
    for row in evidence["rows"]:
        q = qmap.get(row["question_id"])
        if not q: continue
        topic = topics[q["kpi_cluster"]]; topic["attempts"] += 1; topic["correct"] += int(bool(row.get("correct")))
        topic["kpis"][q["kpi_code"]][1] += 1; topic["kpis"][q["kpi_code"]][0] += int(bool(row.get("correct")))
    output = []
    for name, data in topics.items():
        total = len(data.get("total_kpis", set())); studied = len(data.get("studied_kpis", set()))
        coverage = round(100 * studied / total) if total else 0
        qualified = topic_is_qualified(coverage, data["attempts"], total)
        output.append({"topic": name, "correct": data["correct"], "attempts": data["attempts"],
             "accuracy": round(100*data["correct"]/data["attempts"]) if data["attempts"] else None,
             "kpis_studied": studied, "kpis_total": total, "coverage_pct": coverage,
             "qualified": qualified,
             "status": "Limited data" if not qualified else ("Needs work" if data["correct"]/data["attempts"] < .65 else "Developing" if data["correct"]/data["attempts"] < .8 else "Strong"),
             "kpis": [{"code": k, "correct": v[0], "attempts": v[1], "accuracy": round(100*v[0]/v[1])} for k,v in data["kpis"].items()]}
        )
    return output


@practice_bp.get("/api/practice/platform")
def platform_home():
    user, error = require_user()
    if error: return error
    event_id = canonical_event_id(request.args.get("event_id"))
    if not event_id: return jsonify({"error": "Unsupported event"}), 400
    questions, responses, flags, due = _data(user["id"], event_id)
    _, catalog = _supabase_svc("/kpi_catalog", params={"event_id": f"eq.{event_id}", "select": "code,cluster", "limit": "10000"})
    _, completions = _supabase_svc("/user_lesson_completions", params={"user_id": f"eq.{user['id']}", "event_id": f"eq.{event_id}", "lesson_version": "eq.4", "select": "kpi_code", "limit": "10000"})
    catalog = catalog if isinstance(catalog, list) else []
    if not catalog:
        catalog = [{"code": k.get("code"), "cluster": k.get("cluster")} for k in _load_all_kpis()[0] if k.get("event") == event_id]
    completion_codes = {row.get("kpi_code") for row in completions or [] if row.get("kpi_code")}
    topic_by_code = {row.get("code"): row.get("cluster") for row in catalog}
    mastery = [{"kpi_code": code, "kpi_cluster": topic_by_code.get(code, "Other")} for code in completion_codes]
    seen = defaultdict(list)
    for r in responses: seen[r["question_id"]].append(r)
    topics = defaultdict(lambda: {"questions": 0, "kpis": defaultdict(int)})
    for q in questions: topics[q["kpi_cluster"]]["questions"] += 1; topics[q["kpi_cluster"]]["kpis"][q["kpi_code"]] += 1
    _, sets = _supabase_svc("/practice_sets", params={"user_id": f"eq.{user['id']}", "event_id": f"eq.{event_id}", "select": "*", "order": "created_at.desc", "limit": "10"})
    return jsonify({"available": len(questions), "topics": [{"name": k,"questions":v["questions"],"kpis":[{"code":c,"questions":n} for c,n in sorted(v["kpis"].items())]} for k,v in sorted(topics.items())],
                    "history_counts": {"new": sum(q["id"] not in seen for q in questions), "seen": len(seen), "incorrect": sum(bool(rows) and not rows[-1]["correct"] for rows in seen.values()), "flagged": len(flags), "due": len(due)},
                    "difficulty_counts": {d: sum((q.get("empirical_difficulty") or q.get("designed_difficulty")) == d for q in questions) for d in ("easy","medium","hard")},
                    "analysis": sorted(_analytics(questions,responses,catalog,mastery), key=lambda x: (not x["qualified"], x["accuracy"] if x["accuracy"] is not None else 101)),
                    "continue": next((s for s in sets or [] if s["status"] == "active"), None), "recent": [s for s in sets or [] if s["status"] == "completed"][:5]})


def _eligible(questions,responses,flags,due,filters):
    history = set(filters.get("history") or []); topics=set(filters.get("topics") or []); kpis=set(filters.get("kpis") or []); difficulties=set(filters.get("difficulties") or [])
    attempts=defaultdict(list)
    for r in responses: attempts[r["question_id"]].append(r)
    out=[]
    for q in questions:
        qid=q["id"]; states=set()
        if qid not in attempts: states.add("new")
        else: states.add("seen")
        if attempts[qid] and not attempts[qid][-1]["correct"]: states.add("incorrect")
        if qid in flags: states.add("flagged")
        if qid in due: states.add("due")
        difficulty=q.get("empirical_difficulty") or q.get("designed_difficulty")
        if history and not history.intersection(states): continue
        if topics and q["kpi_cluster"] not in topics: continue
        if kpis and q["kpi_code"] not in kpis: continue
        if difficulties and difficulty not in difficulties: continue
        q["_states"]=list(states); out.append(q)
    return out


def _exam_codes(event_id: str) -> set[str]:
    return {
        k["code"] for k in _load_all_kpis()[0]
        if k.get("event") == event_id and "exam" in k.get("eligible_components", [])
    }


@practice_bp.post("/api/practice/sets/preview")
def preview_set():
    user,error=require_user()
    if error:return error
    body=request.get_json(silent=True) or {}; event_id=canonical_event_id(body.get("event_id"))
    if not event_id:return jsonify({"error":"Unsupported event"}),400
    questions,responses,flags,due=_data(user["id"],event_id)
    if body.get("mode") in {"exam", "mock"} or body.get("set_type") == "mock":
        allowed = _exam_codes(event_id); questions = [q for q in questions if q.get("kpi_code") in allowed]
    return jsonify({"available":len(_eligible(questions,responses,flags,due,body.get("filters") or {}))})


@practice_bp.post("/api/practice/sets")
def create_set():
    user,error=require_user()
    if error:return error
    body=request.get_json(silent=True) or {}; event_id=canonical_event_id(body.get("event_id")); set_type=body.get("set_type","custom"); mode=body.get("mode","tutor")
    if not event_id or set_type not in {"smart","custom","mock"} or mode not in {"tutor","exam","mock"}: return jsonify({"error":"Invalid set configuration"}),400
    count=max(1,min(int(body.get("count") or (100 if set_type=="mock" else 10)),100)); questions,responses,flags,due=_data(user["id"],event_id)
    if mode in {"exam", "mock"} or set_type == "mock":
        allowed = _exam_codes(event_id); questions = [q for q in questions if q.get("kpi_code") in allowed]
    filters=body.get("filters") or {}; candidates=_eligible(questions,responses,flags,due,filters)
    attempts=defaultdict(list)
    for r in responses: attempts[r["question_id"]].append(r)
    random.shuffle(candidates)
    if set_type=="smart": candidates.sort(key=lambda q:("new" not in q["_states"],"due" not in q["_states"],"incorrect" not in q["_states"],len(attempts[q["id"]])))
    if len(candidates)<count: return jsonify({"error":f"Only {len(candidates)} unique questions match. Reduce the requested count.","available":len(candidates)}),400
    selected=candidates[:count]; title=body.get("title") or ("Full Mock Exam" if set_type=="mock" else "Smart Practice Questions" if set_type=="smart" else "Custom Practice Questions")
    status,rows=_supabase_svc("/practice_sets",method="POST",payload={"user_id":user["id"],"event_id":event_id,"title":title,"set_type":set_type,"mode":"mock" if set_type=="mock" else mode,"filters":filters,"question_count":count,"time_limit_seconds":5400 if set_type=="mock" else None},prefer="return=representation")
    if status not in (200,201) or not rows:return jsonify({"error":"Practice question set could not be saved"}),502
    practice_set=rows[0]; payload=[{"practice_set_id":practice_set["id"],"user_id":user["id"],"question_id":q["id"],"position":i} for i,q in enumerate(selected)]
    _supabase_svc("/practice_set_questions",method="POST",payload=payload,prefer="return=minimal")
    return jsonify({"set":practice_set}),201


@practice_bp.get("/api/practice/sets/<set_id>")
def get_set(set_id):
    user,error=require_user()
    if error:return error
    event_id = canonical_event_id(request.args.get("event_id"))
    params = {"id":f"eq.{set_id}","user_id":f"eq.{user['id']}","select":"*","limit":"1"}
    if event_id:
        params["event_id"] = f"eq.{event_id}"
    _,sets=_supabase_svc("/practice_sets",params=params)
    if not sets:return jsonify({"error":"Practice question set not found"}),404
    _,items=_supabase_svc("/practice_set_questions",params={"practice_set_id":f"eq.{set_id}","user_id":f"eq.{user['id']}","select":"*","order":"position.asc","limit":"100"})
    ids=[i["question_id"] for i in items or []]; _,questions=_supabase_svc("/kpi_questions",params={"id":f"in.({','.join(ids)})","select":"*","limit":"100"}) if ids else (200,[]); qmap={q["id"]:q for q in questions or []}
    return jsonify({"set":sets[0],"items":[{**item,"question":qmap.get(item["question_id"],{})} for item in items or []]})


@practice_bp.patch("/api/practice/sets/<set_id>/progress")
def update_progress(set_id):
    user,error=require_user()
    if error:return error
    body=request.get_json(silent=True) or {}; position=int(body.get("position",0)); payload={k:body[k] for k in ("selected_index","correct","flagged","response_time_ms","answered_at") if k in body}
    _supabase_svc("/practice_set_questions",method="PATCH",payload=payload,params={"practice_set_id":f"eq.{set_id}","user_id":f"eq.{user['id']}","position":f"eq.{position}"},prefer="return=minimal")
    _supabase_svc("/practice_sets",method="PATCH",payload={"current_index":max(0,position)},params={"id":f"eq.{set_id}","user_id":f"eq.{user['id']}"},prefer="return=minimal")
    return jsonify({"ok":True})


@practice_bp.post("/api/practice/sets/<set_id>/complete")
def complete_set(set_id):
    user,error=require_user()
    if error:return error
    _,sets=_supabase_svc("/practice_sets",params={"id":f"eq.{set_id}","user_id":f"eq.{user['id']}","select":"*","limit":"1"}); _,items=_supabase_svc("/practice_set_questions",params={"practice_set_id":f"eq.{set_id}","user_id":f"eq.{user['id']}","select":"*","limit":"100"})
    if not sets:return jsonify({"error":"Practice question set not found"}),404
    answered=[i for i in items or [] if i.get("selected_index") is not None]; correct=sum(bool(i.get("correct")) for i in answered)
    _supabase_svc("/practice_sets",method="PATCH",payload={"status":"completed","completed_at":now(),"duration_seconds":int((request.get_json(silent=True) or {}).get("duration_seconds") or 0)},params={"id":f"eq.{set_id}","user_id":f"eq.{user['id']}"},prefer="return=minimal")
    ids=[i["question_id"] for i in items or []]; _,questions=_supabase_svc("/kpi_questions",params={"id":f"in.({','.join(ids)})","select":"*","limit":"100"}) if ids else (200,[]); qmap={q["id"]:q for q in questions or []}
    detail_items=[{**item,"question":qmap.get(item["question_id"],{})} for item in items or []]; topic=defaultdict(lambda:[0,0]); kpis=defaultdict(lambda:[0,0])
    for item in detail_items:
        if item.get("selected_index") is None:continue
        q=item["question"]; topic[q["kpi_cluster"]][1]+=1;topic[q["kpi_cluster"]][0]+=int(item["correct"]);kpis[q["kpi_code"]][1]+=1;kpis[q["kpi_code"]][0]+=int(item["correct"])
    return jsonify({"correct":correct,"answered":len(answered),"accuracy":round(100*correct/len(answered)) if answered else 0,"topics":dict(topic),"kpis":dict(kpis),"items":detail_items})


@practice_bp.put("/api/practice/flags/<question_id>")
def flag_question(question_id):
    user,error=require_user()
    if error:return error
    body=request.get_json(silent=True) or {}; event_id=canonical_event_id(body.get("event_id")); flagged=bool(body.get("flagged",True))
    if not event_id:return jsonify({"error":"Unsupported event"}),400
    if flagged:_supabase_svc("/question_flags",method="POST",payload={"user_id":user["id"],"event_id":event_id,"question_id":question_id},params={"on_conflict":"user_id,event_id,question_id"},prefer="resolution=ignore-duplicates,return=minimal")
    else:_supabase_svc("/question_flags",method="DELETE",params={"user_id":f"eq.{user['id']}","event_id":f"eq.{event_id}","question_id":f"eq.{question_id}"},prefer="return=minimal")
    return jsonify({"ok":True,"flagged":flagged})

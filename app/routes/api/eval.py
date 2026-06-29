"""
eval.py — Evaluation endpoints for validating the adaptive learning engine.

Three read-only routes that answer: does predicted mastery correlate with correctness?
Registered on learn_bp, imported at the bottom of learn.py.
"""

from collections import defaultdict

from flask import jsonify, request

from app.db import supabase_rest_request
from app.auth_utils import get_bearer_token, get_current_user
from app.routes.blueprint import learn_bp


@learn_bp.route("/api/eval/calibration", methods=["GET"])  # pyright: ignore[reportUndefinedVariable]
def eval_calibration():
    """
    Per-cluster mean absolute prediction error and overconfidence bias.

    mean_error           = mean(|predicted_mastery - correct|)
    overconfidence_bias  = mean(predicted_mastery - correct)
      positive → system overestimates students
      negative → system underestimates students
    """
    user = get_current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401

    token   = get_bearer_token()
    user_id = user.get("id", "")

    _, rows = supabase_rest_request(
        "/learning_evaluation_log", token=token,
        params={
            "user_id": f"eq.{user_id}",
            "select":  "kpi_cluster,question_type,predicted_mastery,correct,recorded_at",
            "order":   "recorded_at.desc",
            "limit":   "1000",
        },
        prefer="",
    )
    if not isinstance(rows, list) or not rows:
        return jsonify([])

    groups: dict[tuple, list] = defaultdict(list)
    for r in rows:
        key = (r.get("kpi_cluster", ""), r.get("question_type", "recognition"))
        groups[key].append(r)

    result = []
    for (cluster, qtype), group_rows in sorted(groups.items()):
        errors = []
        biases = []
        for r in group_rows:
            pred   = float(r.get("predicted_mastery") or 0.5)
            actual = 1.0 if r.get("correct") else 0.0
            errors.append(abs(pred - actual))
            biases.append(pred - actual)
        result.append({
            "kpi_cluster":         cluster,
            "question_type":       qtype,
            "mean_error":          round(sum(errors) / len(errors), 3),
            "overconfidence_bias": round(sum(biases) / len(biases), 3),
            "sample_count":        len(group_rows),
        })

    return jsonify(result)


@learn_bp.route("/api/eval/prediction", methods=["GET"])  # pyright: ignore[reportUndefinedVariable]
def eval_prediction():
    """
    Raw prediction vs actual for a single KPI, newest-first.
    Query param: kpi_code (required)
    """
    user = get_current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401

    kpi_code = request.args.get("kpi_code", "")
    if not kpi_code:
        return jsonify({"error": "kpi_code required"}), 400

    token   = get_bearer_token()
    user_id = user.get("id", "")

    _, rows = supabase_rest_request(
        "/learning_evaluation_log", token=token,
        params={
            "user_id":  f"eq.{user_id}",
            "kpi_code": f"eq.{kpi_code}",
            "select":   ("question_type,recognition_mastery,application_mastery,"
                         "predicted_mastery,confidence_est,instant_confidence,"
                         "volatility,uncertainty,correct,response_time_ms,recorded_at"),
            "order":    "recorded_at.desc",
            "limit":    "200",
        },
        prefer="",
    )
    return jsonify(rows if isinstance(rows, list) else [])


@learn_bp.route("/api/eval/summary", methods=["GET"])  # pyright: ignore[reportUndefinedVariable]
def eval_summary():
    """
    Three numbers that determine if the system works:
      mean_prediction_error  — |predicted - actual|, lower is better
      overconfidence_bias    — predicted - actual, 0 is ideal
      verdict                — plain-language calibration state
    """
    user = get_current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401

    token   = get_bearer_token()
    user_id = user.get("id", "")

    _, rows = supabase_rest_request(
        "/learning_evaluation_log", token=token,
        params={
            "user_id": f"eq.{user_id}",
            "select":  "question_type,predicted_mastery,correct",
            "order":   "recorded_at.desc",
            "limit":   "2000",
        },
        prefer="",
    )
    if not isinstance(rows, list) or not rows:
        return jsonify({
            "mean_prediction_error": None,
            "overconfidence_bias":   None,
            "sample_count":          0,
            "by_question_type":      {},
            "verdict":               "insufficient_data",
        })

    all_errors, all_biases = [], []
    by_type: dict[str, dict] = {}

    for r in rows:
        qtype  = r.get("question_type", "recognition")
        pred   = float(r.get("predicted_mastery") or 0.5)
        actual = 1.0 if r.get("correct") else 0.0
        err    = abs(pred - actual)
        bias   = pred - actual
        all_errors.append(err)
        all_biases.append(bias)
        if qtype not in by_type:
            by_type[qtype] = {"errors": [], "biases": []}
        by_type[qtype]["errors"].append(err)
        by_type[qtype]["biases"].append(bias)

    mean_err  = round(sum(all_errors) / len(all_errors), 3)
    mean_bias = round(sum(all_biases) / len(all_biases), 3)

    by_type_out = {}
    for qtype, vals in by_type.items():
        n = len(vals["errors"])
        by_type_out[qtype] = {
            "mean_error": round(sum(vals["errors"]) / n, 3),
            "bias":       round(sum(vals["biases"]) / n, 3),
            "n":          n,
        }

    if len(rows) < 50:
        verdict = "collecting_data"
    elif mean_err < 0.15:
        verdict = "well_calibrated"
    elif mean_err < 0.25:
        verdict = "acceptable"
    elif mean_bias > 0.20:
        verdict = "overconfident — system overestimates student readiness"
    elif mean_bias < -0.20:
        verdict = "underconfident — system underestimates strong learners"
    else:
        verdict = "noisy — high error, no clear directional bias"

    return jsonify({
        "mean_prediction_error": mean_err,
        "overconfidence_bias":   mean_bias,
        "sample_count":          len(rows),
        "by_question_type":      by_type_out,
        "verdict":               verdict,
    })

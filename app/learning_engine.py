"""
learning_engine.py — Layers 2–5 of the adaptive learning system.

Layer 2: Feature extraction (speed_ratio, hesitation, revision)
Layer 3: Inference (confidence, mastery, uncertainty)
Layer 4: SRS policy (quality score, dampening, floor)
Layer 5: Calibration proposals (human-review only)
"""

import hashlib
import statistics
from datetime import datetime, timezone

# ── Constants ──────────────────────────────────────────────────────────────────

EWMA_ALPHA              = 0.15   # weight of newest sample in baseline
MIN_PROGRESS_MULTIPLIER = 0.85   # dampening floor — system can slow but not stall progress

# Contradiction reconciliation thresholds
RECONCILIATION_MASTERY_THRESHOLD = 0.8
RECONCILIATION_SRS_REPEAT_FLOOR  = 5
RECONCILIATION_MASTERY_CAP       = 0.75

CALIBRATION_THRESHOLDS = {
    "single_user_bias_gap":  0.20,
    "multi_user_bias_gap":   0.15,
    "min_cluster_sample":    15,
    "escalation_user_count": 3,
}


# ── Layer 1: Idempotency hash (server-side) ────────────────────────────────────

def make_idempotency_hash(user_id: str, session_id: str, question_id: str,
                           correct: bool, answered_at: datetime) -> str:
    """Generate server-side idempotency key. Floor timestamp to 10s to absorb drift."""
    floored = int(answered_at.timestamp() // 10) * 10
    raw = f"{user_id}:{session_id}:{question_id}:{correct}:{floored}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


# ── Layer 2: Feature extraction ────────────────────────────────────────────────

def extract_features(response_time_ms: int, time_to_first_ms: int | None,
                     answer_change_count: int, baseline_ms: int) -> dict:
    """
    Convert raw timing into normalized behavioral signals.
    All outputs are 0–1 floats. speed_ratio > 1 = slower than baseline.
    """
    baseline = max(baseline_ms, 1000)
    speed_ratio     = response_time_ms / baseline
    hesitation      = (time_to_first_ms or 0) / max(response_time_ms, 1)
    revision_index  = min(answer_change_count / 3.0, 1.0)

    return {
        "speed_ratio":      round(speed_ratio, 3),
        "hesitation_index": round(hesitation, 3),
        "revision_index":   round(revision_index, 3),
    }


# ── Layer 2b: Baseline update (EWMA with cold-start shrinkage) ───────────────

def update_baseline(current_ms: int, new_sample_ms: int, sample_count: int) -> int:
    """
    EWMA baseline with cold-start shrinkage.
    Early samples use a decaying alpha so outliers don't permanently anchor
    the baseline. After ~20 samples the fixed EWMA_ALPHA takes over.
    """
    baseline = current_ms if sample_count > 0 else 12000
    alpha = min(EWMA_ALPHA, 1.0 / (sample_count + 1))
    return round(alpha * new_sample_ms + (1 - alpha) * baseline)


# ── Layer 3: Inference ────────────────────────────────────────────────────────

def infer_instant_confidence(features: dict, correct: bool) -> float:
    """
    How deliberate was THIS answer?
    Penalties are additive and capped — correlated signals don't stack infinitely.
    Returns 0.0–1.0.
    """
    s = features["speed_ratio"]
    h = features["hesitation_index"]
    r = features["revision_index"]

    penalty = min(h + r + max(s - 1.0, 0) * 0.3, 0.80)
    instant = max(0.10, 1.0 - penalty)
    return round(instant, 3)


def compute_stability_confidence(recent_instant_scores: list[float]) -> dict:
    """
    How consistent has the student's confidence signal been recently?
    Returns {"value": float | None, "state": str}
    Never returns bare None — callers must handle state field.
    Variance is clamped to 0.25 to prevent collapse under noisy users.
    """
    if len(recent_instant_scores) < 4:
        return {"value": None, "state": "insufficient_data"}
    raw_variance = statistics.variance(recent_instant_scores)
    # Clamp: variance above 0.25 already signals near-total instability;
    # letting it grow further would push value below 0 and break downstream logic.
    scaled = min(raw_variance, 0.25)
    value = round(max(0.0, 1.0 - scaled * 4), 3)
    return {"value": value, "state": "ok"}


def update_mastery(prev_mastery: float, correct: bool, confidence: float) -> float:
    """
    Rolling mastery estimate. Single answer moves it 30%, prior state 70%.

    Authority: confidence_est (EMA) only. Tensions do NOT touch mastery —
    they belong to queue scheduling. Mixing them here creates signal entanglement
    where one bad response influences inference, policy, and scheduling
    simultaneously, making the system overreactive and hard to debug.
    """
    signal = confidence if correct else (1.0 - confidence) * 0.3
    new_mastery = 0.7 * prev_mastery + 0.3 * signal
    return round(max(0.0, min(1.0, new_mastery)), 3)


def update_recognition_mastery(prev: float, correct: bool,
                                confidence: float) -> float:
    """
    Mastery estimate scoped to recognition questions only.

    Separated from application_mastery so the system can distinguish
    'knows the term' from 'can apply the concept'. Without this split,
    a student who memorizes vocabulary perfectly looks mastered even if
    they fail every application scenario — a direct competition-readiness flaw.

    Same rolling formula as update_mastery; kept separate so DB columns
    and calibration curves remain independent axes, not one blended signal.
    """
    return update_mastery(prev, correct, confidence)


def update_application_mastery(prev: float, correct: bool,
                                confidence: float) -> float:
    """
    Mastery estimate scoped to application questions only.

    Application questions test transfer ability, not familiarity. Tracking
    this separately lets the system detect the common DECA failure pattern:
    strong recognition, weak application — which looks like 'mastered' in a
    blended score but predicts poor competition performance.

    Same formula; separate column so each axis can be calibrated and
    thresholded independently without redesigning the inference engine.
    """
    return update_mastery(prev, correct, confidence)


def update_confidence_ema(prev_confidence_est: float, instant_conf: float,
                          sample_count: int) -> float:
    """
    Smooth the confidence estimate over time using the same cold-start shrinkage
    as the timing baseline. This is what gets stored as confidence_est.

    Separation of concerns:
      confidence_est          = history-smoothed signal (stable, used in inference)
      last_instant_confidence = raw signal from this answer (stored separately)

    Without this split, confidence_est becomes meaningless within weeks — it just
    echoes the most recent answer instead of representing the student's trend.
    """
    alpha = min(EWMA_ALPHA, 1.0 / (sample_count + 1))
    smoothed = alpha * instant_conf + (1 - alpha) * prev_confidence_est
    return round(max(0.0, min(1.0, smoothed)), 3)


def compute_confidence_volatility(instant_conf: float,
                                   confidence_est: float) -> float:
    """
    Guard signal for the false-stability trap.

    EMA smooths out exactly what we need to detect: guessing bursts, confusion
    spikes, sudden mastery drops. This metric captures that gap so dampening
    can react to it without contaminating the mastery or quality score.

    Authority: dampening ONLY — not mastery, not SRS quality, not tensions.

    Scaling: (raw ** 1.5) + 0.05 * raw
      — The power term makes sustained divergence escalate nonlinearly.
      — The linear term keeps early/weak signals alive instead of vanishing
        in the dead zone below ~0.1. Early learners operate in exactly that
        band, so pure power scaling would leave them unguarded.
    Returns 0.0–1.0.
    """
    raw = abs(instant_conf - confidence_est)
    return round(min((raw ** 1.5) + 0.05 * raw, 1.0), 3)


def compute_uncertainty(mastery: float, confidence: float,
                        stability: dict) -> float:
    """
    How much should we trust the inference signals?
    High uncertainty = signals conflict or we have too little data.
    """
    if stability["state"] == "insufficient_data":
        return 1.0  # explicitly unknown

    signal_gap   = abs(mastery - confidence)
    instability  = 1.0 - (stability["value"] or 0.5)
    uncertainty  = (signal_gap * 0.6 + instability * 0.4)
    return round(min(1.0, uncertainty), 3)


# ── Layer 3b: Tension classification ─────────────────────────────────────────

def classify_tensions(mastery: float, confidence: float,
                      uncertainty: float) -> dict[str, float]:
    """
    Each tension type is independent. Do NOT aggregate into one number.
    Callers use each type separately in Layer 4.

    Precedence rule: if signal tension exists, calibration and behavioral are
    suppressed. Signal means the data is too noisy to distinguish the other
    two types — acting on them simultaneously produces conflicting policy actions.
    """
    tensions = {}

    if uncertainty > 0.70:
        # Signal tension dominates — return early, suppress other types
        tensions["signal"] = round(uncertainty, 3)
        return tensions

    if abs(mastery - confidence) > 0.30:
        tensions["calibration"] = round(abs(mastery - confidence), 3)
    if uncertainty > 0.60 and confidence > 0.50:
        tensions["behavioral"] = round(uncertainty, 3)

    return tensions


# ── Layer 4: SRS policy ───────────────────────────────────────────────────────

def srs_quality_score(correct: bool, confidence: float) -> int:
    """
    SM-2 quality integer 0–5.
    Correct answers always score 3–5. Wrong always 0–2.
    Confidence shifts the magnitude within each band.
    """
    if correct:
        return 3 + round(confidence * 2)
    else:
        return round(confidence * 2)  # wrong + high conf = 2 (hard penalty)


def compute_dampening(uncertainty: float, tensions: dict,
                      stability: dict,
                      confidence_volatility: float = 0.0) -> float:
    """
    Dampening factor applied to SM-2 quality score before compute_sm2.

    Inputs:
      uncertainty           — from compute_uncertainty (uses EMA confidence)
      tensions              — from classify_tensions
      stability             — from compute_stability_confidence
      confidence_volatility — from compute_confidence_volatility (raw vs EMA gap)

    Volatility is the guard against the false-stability trap: EMA looks fine
    but the student is actually guessing. It only affects interval control,
    never mastery or quality band.

    Floor is MIN_PROGRESS_MULTIPLIER (0.85), not MAX_DAMPENING (0.60).
    MAX_DAMPENING is the absolute lower bound; MIN_PROGRESS_MULTIPLIER ensures
    the system can slow progress but never stall it — critical for weak students
    who would otherwise get stuck in compounding dampening loops.
    """
    if stability["state"] == "insufficient_data":
        return 1.0  # uncalibrated — don't penalize yet

    dampening = 1.0

    # Uncertainty reduces confidence in the quality signal
    dampening -= uncertainty * 0.25

    # Volatility guard: catches confusion spikes EMA hides.
    # Nonlinear (** 1.5 applied upstream) so single spikes barely register
    # but sustained guessing bursts escalate. Cap at 0.15 max reduction.
    dampening -= min(confidence_volatility * 0.20, 0.15)

    # Per-tension adjustments (independent, not summed; signal is mutually exclusive
    # with calibration/behavioral due to classify_tensions precedence rule)
    if "calibration" in tensions:
        dampening *= 0.80
    if "behavioral" in tensions:
        dampening *= 0.88
    if "signal" in tensions:
        dampening *= 0.92

    # MIN_PROGRESS_MULTIPLIER guarantees forward motion even under max noise (fix 2)
    return round(max(MIN_PROGRESS_MULTIPLIER, min(1.0, dampening)), 3)


def reconcile_mastery(mastery: float, srs_correct_attempts: int,
                      srs_total_attempts: int) -> float:
    """
    Bidirectional contradiction reconciliation.

    Grounds inference in observed SRS behavior in both directions:

    DOWN — mastery looks high but item keeps failing:
      Inference has drifted above reality. Cap at 0.75 to force re-exposure
      before the SRS extends the interval further.

    UP — mastery looks low but item is being retained well:
      Inference is underestimating a student who hesitates (slow responders,
      application-heavy learners). Floor at 0.65 to prevent the system from
      permanently penalising strong learners with a slow behavioral profile.

    Neither direction is a permanent change — mastery recovers or decays
    normally on the next answer. This is a one-step correction per answer,
    not a rewrite of history.
    """
    if srs_total_attempts < RECONCILIATION_SRS_REPEAT_FLOOR:
        return mastery  # not enough data to reconcile yet

    correct_rate = srs_correct_attempts / srs_total_attempts

    # Downward correction: high mastery, poor SRS performance
    if (mastery > RECONCILIATION_MASTERY_THRESHOLD
            and correct_rate < 0.40):
        return min(mastery, RECONCILIATION_MASTERY_CAP)

    # Upward correction: low mastery, strong SRS retention
    if mastery < 0.60 and correct_rate > 0.85:
        return max(mastery, 0.65)

    return mastery


def apply_dampened_quality(quality: int, dampening: float) -> int:
    """
    Scale the SM-2 quality input by dampening before passing to compute_sm2.

    This keeps ease_factor and interval in sync — both respond to the same
    dampened signal, so the SRS state stays internally consistent.

    Minimum quality of 1 preserves the direction of the signal even at max dampening.
    """
    return max(1, round(quality * dampening))


# ── Layer 4b: Tension-driven queue adjustments ────────────────────────────────

TENSION_POLICY = {
    # calibration tension: student may be pattern-matching
    # → increase recognition weight to test actual recall
    "calibration": {"action": "increase_recognition_weight"},
    # behavioral tension: student is inconsistent, not miscalibrated
    # → no question type change, just dampen interval
    "behavioral":  {"action": "none"},
    # signal tension: too noisy to trust application judgment
    # → defer application questions until signals stabilize
    "signal":      {"action": "defer_application_questions"},
}


def get_queue_adjustments(tensions: dict) -> list[str]:
    """Return action strings for the session queue to act on."""
    actions = []
    for tension_type, policy in TENSION_POLICY.items():
        if tension_type in tensions and policy["action"] != "none":
            actions.append(policy["action"])
    return actions


# ── Layer 5: Calibration observer (human-review only) ─────────────────────────

def calibration_proposals(rows: list[dict]) -> list[dict]:
    """
    rows: list of {kpi_cluster, avg_confidence, actual_accuracy, sample_count, user_count}
    Returns proposals for human review. NOT fed back into the system.
    """
    proposals = []
    for row in rows:
        if row["sample_count"] < CALIBRATION_THRESHOLDS["min_cluster_sample"]:
            continue

        gap = row["avg_confidence"] - row["actual_accuracy"]
        threshold = (
            CALIBRATION_THRESHOLDS["multi_user_bias_gap"]
            if row.get("user_count", 1) > 1
            else CALIBRATION_THRESHOLDS["single_user_bias_gap"]
        )

        if abs(gap) < threshold:
            continue

        proposal = {
            "cluster":   row["kpi_cluster"],
            "direction": "overestimating" if gap > 0 else "underestimating",
            "magnitude": round(abs(gap), 3),
            "note":      f"conf {row['avg_confidence']:.2f} vs accuracy {row['actual_accuracy']:.2f}",
            "action_required": row.get("user_count", 1) >= CALIBRATION_THRESHOLDS["escalation_user_count"],
        }
        proposals.append(proposal)

    return proposals

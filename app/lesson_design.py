"""App-owned lesson design rules for Learn Mode.

The model fills these slots; it does not decide the lesson shape.
"""

from __future__ import annotations


QUICK_VERBS = {
    "define",
    "describe",
    "discuss",
    "explain",
    "identify",
    "recognize",
}

STANDARD_VERBS = {
    "apply",
    "compare",
    "demonstrate",
    "determine",
    "interpret",
    "prepare",
    "use",
}

DEEP_VERBS = {
    "analyze",
    "calculate",
    "develop",
    "evaluate",
    "manage",
    "plan",
    "prepare",
}

COMMUNICATION_HINTS = {"communicat", "demonstrate", "handle", "respond", "objection", "presentation", "negot"}
PROCESS_HINTS = {"process", "procedure", "steps", "selling", "channel", "workflow"}
DATA_HINTS = {"calculate", "financial statement", "gross profit", "ratio", "budget", "forecast", "cash flow"}
DECISION_HINTS = {"decide", "determine", "select", "solve", "problem", "risk", "strategy"}
ANALYSIS_HINTS = {"analyze", "assess", "diagnose", "evaluate", "interpret", "investigate"}

ARCHETYPE_BY_SKILL = {
    "concept": "concept_discovery",
    "decision": "decision_lab",
    "communication": "communication_coach",
    "process": "build_process",
    "calculation_data": "numbers_lab",
    "analysis": "diagnose_problem",
}

ACTION_BY_SKILL = {
    "concept": "classify",
    "decision": "choose",
    "communication": "respond",
    "process": "sequence",
    "calculation_data": "calculate",
    "analysis": "diagnose",
}


def _first_word(text: str) -> str:
    return (text or "").strip().split(" ", 1)[0].lower().strip(":;,.")


def classify_kpi(text: str) -> dict:
    """Return a conservative complexity + skill type for a KPI."""
    normalized = (text or "").lower()
    verb = _first_word(normalized)

    if verb in DEEP_VERBS or any(hint in normalized for hint in DATA_HINTS):
        complexity = "deep"
    elif verb in STANDARD_VERBS:
        complexity = "standard"
    else:
        complexity = "quick" if verb in QUICK_VERBS else "standard"

    if any(hint in normalized for hint in DATA_HINTS):
        skill_type = "calculation_data"
    elif any(hint in normalized for hint in ANALYSIS_HINTS):
        skill_type = "analysis"
    elif any(hint in normalized for hint in COMMUNICATION_HINTS):
        skill_type = "communication"
    elif any(hint in normalized for hint in PROCESS_HINTS):
        skill_type = "process"
    elif any(hint in normalized for hint in DECISION_HINTS):
        skill_type = "decision"
    else:
        skill_type = "concept"

    target_minutes = {"quick": "2-3", "standard": "3-5", "deep": "5-7"}[complexity]
    deca_action = {
        "concept": "explain",
        "decision": "recommend",
        "communication": "demonstrate",
        "process": "demonstrate",
        "calculation_data": "calculate",
        "analysis": "analyze",
    }[skill_type]
    primary_archetype = ARCHETYPE_BY_SKILL[skill_type]
    interactions = {
        "concept_discovery": ["predict", "classify", "choose"],
        "decision_lab": ["predict", "choose", "compare"],
        "communication_coach": ["choose", "respond", "compare"],
        "build_process": ["sequence", "predict", "choose"],
        "numbers_lab": ["predict", "calculate", "diagnose"],
        "diagnose_problem": ["inspect", "diagnose", "choose"],
    }[primary_archetype]
    return {
        "complexity": complexity,
        "skill_type": skill_type,
        "target_minutes": target_minutes,
        "primary_archetype": primary_archetype,
        "learner_action": ACTION_BY_SKILL[skill_type],
        "deca_action": deca_action,
        "recommended_interactions": interactions,
        "required_block_count": {"quick": 2, "standard": 3, "deep": 4}[complexity],
        "vocab_mode": "embedded" if complexity == "quick" else "preteach",
        "vocab_count": {"quick": 3, "standard": 4, "deep": 5}[complexity],
    }


def build_lesson_prompt(
    *,
    code: str,
    text: str,
    cluster: str,
    standard: str,
    deca_cluster: str,
    lesson_design: dict,
) -> str:
    """Build the fixed-slot prompt used by AI lesson generation."""
    complexity = lesson_design["complexity"]
    skill_type = lesson_design["skill_type"]
    target_minutes = lesson_design["target_minutes"]
    primary_archetype = lesson_design["primary_archetype"]
    learner_action = lesson_design["learner_action"]
    deca_action = lesson_design["deca_action"]
    recommended_interactions = ", ".join(lesson_design["recommended_interactions"])
    recommended_interactions_json = ", ".join(
        f'"{interaction}"' for interaction in lesson_design["recommended_interactions"]
    )
    required_block_count = int(lesson_design.get("required_block_count") or {"quick": 2, "standard": 3, "deep": 4}[complexity])
    vocab_count = int(lesson_design.get("vocab_count") or {"quick": 3, "standard": 4, "deep": 5}[complexity])
    deca_cluster = deca_cluster or "Business"
    return f"""You are a DECA competition coach creating a structured, interactive lesson for high school students.

The app owns the lesson structure. You only fill the requested JSON slots.

KPI:
- Code: {code}
- Text: {text}
- Subject Cluster: {cluster}
- Standard: {standard}
- DECA Cluster: {deca_cluster}
- Complexity: {complexity}
- Skill type: {skill_type}
- Target time: {target_minutes} minutes
- Learning archetype: {primary_archetype}
- Learner action: {learner_action}
- DECA transfer action: {deca_action}
- Recommended interactions: {recommended_interactions}

Return ONLY valid JSON with this exact structure:

{{
  "lesson_design": {{
    "complexity": "{complexity}",
    "skill_type": "{skill_type}",
    "target_minutes": "{target_minutes}"
  }},
  "instructional_plan": {{
    "primary_archetype": "{primary_archetype}",
    "learner_action": "{learner_action}",
    "deca_action": "{deca_action}",
    "recommended_interactions": [{recommended_interactions_json}]
  }},
  "mission": {{
    "title": "A short action-oriented mission title.",
    "brief": "A realistic business problem, 55 words maximum, that creates curiosity before naming or defining the KPI.",
    "opening_interaction": {{
      "question": "A prediction or decision the student can make immediately.",
      "choices": ["Choice A", "Choice B", "Choice C"],
      "correct": 1,
      "explanation": "Explain the mechanism revealed by the decision, not just which answer is correct.",
      "choice_feedback": ["Specific response to choice A", "Specific response to choice B", "Specific response to choice C"],
      "aha": "One memorable sentence beginning with This is why or That is why."
    }}
  }},
  "hook": "A concise bridge from the opening decision to the KPI, 35 words maximum.",
  "vocab": [
    {{"term": "Essential Term 1", "definition": "Clear one-sentence definition", "importance": "essential"}},
    {{"term": "Essential Term 2", "definition": "Clear one-sentence definition", "importance": "essential"}},
    {{"term": "Supporting Term", "definition": "Clear one-sentence definition", "importance": "supporting"}}
  ],
  "learning_blocks": [
    {{"type": "concept_reveal", "title": "Short heading", "body": "Knowledge-dense plain-English block, maximum 70 words."}},
    {{"type": "consequence", "title": "Short heading", "body": "Knowledge-dense plain-English block, maximum 70 words."}}
  ],
  "concept": {{
    "summary": "One clear sentence explaining what this KPI is about.",
    "explanation": "A knowledge-rich explanation, maximum 120 words, that teaches the essential mechanism, why it matters, and connects the KPI to the hook without filler.",
    "bullets": ["Key insight 1", "Key insight 2", "Key insight 3"],
    "table": [
      {{"term": "Term 1", "definition": "Brief definition"}},
      {{"term": "Term 2", "definition": "Brief definition"}},
      {{"term": "Term 3", "definition": "Brief definition"}}
    ],
    "concept_check": {{
      "question": "One short question testing the core idea.",
      "choices": ["Choice A", "Choice B", "Choice C", "Choice D"],
      "correct": 0,
      "explanation": "One sentence explaining why this is correct."
    }}
  }},
  "interactive_check": {{
    "question": "One quick learning check during the lesson.",
    "choices": ["Choice A", "Choice B", "Choice C"],
    "correct": 0,
    "explanation": "Explain why the correct choice fits."
  }},
  "realistic_example": {{
    "story": "A concrete realistic business example using familiar student context such as restaurants, school events, clothing, sports, gaming, social media, gyms, or small businesses.",
    "flow": ["Observation", "Customer group or decision", "Business action"]
  }},
  "mini_roleplay": {{
    "role": "Student's business role",
    "setup": "A tiny business situation the student must navigate.",
    "decisions": [
      {{
        "situation": "What happens first, possibly including brief dialogue.",
        "question": "What should you do?",
        "choices": ["Response A", "Response B", "Response C"],
        "correct": 1,
        "explanation": "Why the best response works.",
        "consequence": "What changes after the choice."
      }},
      {{
        "situation": "A follow-up consequence or customer/manager response.",
        "question": "What should you do next?",
        "choices": ["Response A", "Response B", "Response C"],
        "correct": 0,
        "explanation": "Why the best response works.",
        "consequence": "How the situation resolves."
      }}
    ],
    "why_it_matters": "Connect the roleplay back to the KPI."
  }},
  "key_takeaways": ["Takeaway 1", "Takeaway 2", "Takeaway 3"],
  "practice_questions": [
    {{
      "text": "Question 1: Understand. Can the student recognize the concept?",
      "choices": ["Choice A", "Choice B", "Choice C", "Choice D"],
      "correct": 0,
      "explanation": "Explain why the correct answer works and the distractors are weaker.",
      "kpi_code": "{code}",
      "kpi_text": "{text}",
      "cluster": "{cluster}",
      "deca_cluster": "{deca_cluster}"
    }},
    {{
      "text": "Question 2: Apply. A realistic scenario where the student uses the KPI.",
      "choices": ["Choice A", "Choice B", "Choice C", "Choice D"],
      "correct": 1,
      "explanation": "Explain the business reasoning and why the distractors are weaker.",
      "kpi_code": "{code}",
      "kpi_text": "{text}",
      "cluster": "{cluster}",
      "deca_cluster": "{deca_cluster}"
    }},
    {{
      "text": "Question 3: DECA Challenge. A role-specific competition-style scenario with plausible distractors.",
      "choices": ["Choice A", "Choice B", "Choice C", "Choice D"],
      "correct": 2,
      "explanation": "Explain the competition-level reasoning and why the distractors are weaker.",
      "kpi_code": "{code}",
      "kpi_text": "{text}",
      "cluster": "{cluster}",
      "deca_cluster": "{deca_cluster}"
    }}
  ]
}}

Rules:
- Be concise but substantive: maximize useful business knowledge per sentence.
- Prefer precise definitions, mechanisms, tradeoffs, and concrete examples over motivational filler.
- Do not repeat the same idea across the hook, blocks, explanation, bullets, and takeaways.
- Keep vocabulary definitions to one precise sentence each.
- Generate exactly {vocab_count} vocabulary terms; do not pad the list.
- The mission must frame the KPI as a business problem, not announce a school lesson.
- The opening interaction must come before the definition and make the learner predict, diagnose, or decide.
- Match the lesson behavior to {primary_archetype}; changing only scenario nouns is not sufficient.
- Label each learning block with one of: concept_reveal, evidence, compare, consequence, misconception, deca_tip.
- The DECA Challenge must require the student to {deca_action}, at multiple-choice depth for this no-typing flow.
- Do not pad easy KPIs. Target time is a guide, not a rule.
- Teach through: situation -> discover -> decide -> see consequence -> prove it.
- Make generated examples realistic, not falsely claimed as real.
- Generate exactly {required_block_count} learning_blocks. The app, not the model, owns this count.
- mini_roleplay: quick=1 decision, standard=2 decisions, deep=2-3 decisions.
- practice_questions: generate EXACTLY 3 final questions:
  1. Check / understanding / recognition of this KPI's learner action, not a generic topic quiz
  2. Apply / scenario that requires the student to {learner_action}
  3. DECA Challenge / harder role-specific scenario that requires the student to {deca_action}
- All practice questions: four plausible choices, only one correct. Distractors should be realistic business mistakes, never joke answers.
- Wrong-answer explanations should name the misconception without wasting words.
"""

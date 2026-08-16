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

COMMUNICATION_HINTS = {"communicat", "customer", "relation", "objection", "presentation", "negot"}
PROCESS_HINTS = {"process", "procedure", "steps", "selling", "channel", "workflow"}
DATA_HINTS = {"calculate", "financial statement", "gross profit", "ratio", "budget", "forecast", "cash flow"}
DECISION_HINTS = {"decide", "determine", "select", "solve", "problem", "risk", "strategy"}


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
    elif any(hint in normalized for hint in COMMUNICATION_HINTS):
        skill_type = "communication"
    elif any(hint in normalized for hint in PROCESS_HINTS):
        skill_type = "process"
    elif any(hint in normalized for hint in DECISION_HINTS):
        skill_type = "decision"
    else:
        skill_type = "concept"

    target_minutes = {"quick": "5-7", "standard": "8-10", "deep": "10-13"}[complexity]
    return {
        "complexity": complexity,
        "skill_type": skill_type,
        "target_minutes": target_minutes,
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

Return ONLY valid JSON with this exact structure:

{{
  "lesson_design": {{
    "complexity": "{complexity}",
    "skill_type": "{skill_type}",
    "target_minutes": "{target_minutes}"
  }},
  "hook": "A realistic student-relevant business situation, 40 words maximum. Do not claim it is a real story unless it is obviously generic.",
  "vocab": [
    {{"term": "Key Term 1", "definition": "Clear definition"}},
    {{"term": "Key Term 2", "definition": "Clear definition"}},
    {{"term": "Key Term 3", "definition": "Clear definition"}},
    {{"term": "Key Term 4", "definition": "Clear definition"}},
    {{"term": "Key Term 5", "definition": "Clear definition"}},
    {{"term": "Key Term 6", "definition": "Clear definition"}}
  ],
  "learning_blocks": [
    {{"title": "Short heading", "body": "Knowledge-dense plain-English block, maximum 70 words."}},
    {{"title": "Short heading", "body": "Knowledge-dense plain-English block, maximum 70 words."}}
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
- Do not pad easy KPIs. Target time is a guide, not a rule.
- Teach through: situation -> discover -> decide -> see consequence -> prove it.
- Make generated examples realistic, not falsely claimed as real.
- learning_blocks: quick=2 blocks, standard=2-3 blocks, deep=3-4 blocks.
- mini_roleplay: quick=1 decision, standard=2 decisions, deep=2-3 decisions.
- practice_questions: generate EXACTLY 3 final questions:
  1. Check / understanding / recognition
  2. Apply / scenario
  3. DECA Challenge / harder role-specific scenario
- All practice questions: four plausible choices, only one correct."""

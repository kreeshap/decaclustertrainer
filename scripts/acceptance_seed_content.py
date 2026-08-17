"""Reviewed minimum production fixture for the adaptive-planner acceptance test."""

from app.learn_validation import validate_lesson
from app.lesson_design import classify_kpi

EVENT_ID = "financial_services_tdm"
KPI_ID = "financial_services_tdm:BL:163"
KPI_CODE = "BL:163"
KPI_TEXT = "Comply with the spirit and intent of laws and regulations"
KPI_CLUSTER = "Business Law (BL)"

LESSON = {
    "lesson_design": {"complexity": "standard", "skill_type": "concept", "target_minutes": "3-5"},
    "instructional_plan": {"primary_archetype": "concept_discovery", "learner_action": "classify", "deca_action": "explain", "recommended_interactions": ["predict", "classify", "choose"]},
    "mission": {"title": "The loophole decision", "brief": "A financial services firm finds a disclosure loophole that is technically permitted but would hide a fee from customers. Decide whether using it protects the company or creates a larger business risk.", "opening_interaction": {"question": "What should the manager do?", "choices": ["Use the loophole because it is technically legal", "Disclose the fee clearly and follow the law's purpose", "Wait until a customer complains"], "correct": 1, "explanation": "Following both the wording and purpose of the rule protects customers and reduces enforcement and reputation risk.", "choice_feedback": ["Technical compliance alone can still violate regulatory intent and customer trust.", "Correct: transparent disclosure matches both the rule and its protective purpose.", "Waiting transfers avoidable risk to customers and the firm."], "aha": "This is why ethical compliance asks what a rule is designed to protect, not only what its words permit."}},
    "hook": "Strong compliance decisions satisfy the written requirement while also protecting the people and market behavior the rule was created to safeguard.",
    "vocab": [
        {"term": "Letter of the law", "definition": "The exact written requirements contained in a law or regulation.", "importance": "essential"},
        {"term": "Spirit of the law", "definition": "The underlying purpose and public interest a legal requirement is meant to serve.", "importance": "essential"},
        {"term": "Regulatory compliance", "definition": "The systems and actions a business uses to meet applicable legal and regulatory obligations.", "importance": "essential"},
        {"term": "Reputational risk", "definition": "Potential damage to trust and business value caused by conduct stakeholders view as improper.", "importance": "supporting"},
    ],
    "learning_blocks": [
        {"type": "concept_reveal", "title": "Two standards of compliance", "body": "The letter of the law asks whether conduct meets the rule's written language. The spirit of the law asks whether conduct also respects the protection or outcome lawmakers intended. Responsible firms examine both before acting."},
        {"type": "mechanism", "title": "How managers decide", "body": "Managers identify the governing rule, determine who it protects, test whether the proposed action defeats that protection, document the reasoning, and choose the transparent option when a technical loophole conflicts with regulatory purpose."},
        {"type": "consequence", "title": "Why technical legality is not enough", "body": "Exploiting loopholes can trigger regulator scrutiny, lawsuits, corrective costs, customer losses, and stricter future rules. Conduct aligned with legal intent supports trust, consistent decisions, and sustainable relationships with customers and regulators."},
    ],
    "concept": {"summary": "Businesses should meet legal requirements in both wording and intended purpose.", "explanation": "Compliance is more than avoiding an explicit prohibition. A manager should identify the applicable rule, understand the harm or stakeholder it protects, and evaluate whether a proposed action undermines that purpose. A loophole that recreates the harm creates legal, ethical, and strategic risk. Policies, training, documentation, monitoring, and escalation help a firm apply this judgment consistently.", "bullets": ["Identify both the written rule and its protective purpose.", "Reject technical workarounds that recreate the harm the rule addresses.", "Document and communicate decisions so compliance is consistent."], "table": [{"term": "Letter", "definition": "Exact wording"}, {"term": "Spirit", "definition": "Intended protection"}, {"term": "Compliance controls", "definition": "Policies and checks that guide conduct"}]},
    "realistic_example": {"story": "A student-run credit union simulation charges a service fee. The team could bury it in a long digital agreement, but instead places the amount beside the confirmation button and trains staff to explain it before enrollment.", "flow": ["Identify the disclosure requirement", "Recognize that informed consent is the protected outcome", "Show and explain the fee before acceptance"]},
    "mini_roleplay": {"role": "Compliance analyst", "setup": "Your manager proposes placing an account fee only in dense terms because the disclosure is technically present.", "decisions": [{"situation": "The manager says competitors use the same placement.", "question": "How should you respond?", "choices": ["Approve it without review", "Recommend prominent disclosure and explain the customer-protection purpose", "Delete the fee"], "correct": 1, "explanation": "Prominent disclosure satisfies the requirement's protective purpose while preserving the business decision.", "consequence": "The manager asks for a practical implementation."}, {"situation": "The team must choose where the fee appears.", "question": "What should happen next?", "choices": ["Display it before confirmation and test comprehension", "Place it after enrollment", "Mention it only in staff notes"], "correct": 0, "explanation": "Advance display and testing make the disclosure meaningful rather than merely technical.", "consequence": "Customers can make an informed decision and the firm keeps evidence of effective compliance."}], "why_it_matters": "DECA judges reward recommendations that connect law, stakeholder protection, implementation, and business risk."},
    "key_takeaways": ["Comply with both a rule's wording and purpose.", "Evaluate who the rule protects and what harm it prevents.", "Use transparent controls instead of technical loopholes."],
    "practice_questions": [
        {"text": "What best distinguishes the spirit of a law from its letter?", "choices": ["The spirit reflects the law's intended protection", "The spirit applies only to criminal law", "The spirit replaces written requirements", "The spirit is an optional company slogan"], "correct": 0, "explanation": "The spirit is the purpose and protective outcome behind the written rule; it complements rather than replaces the letter."},
        {"text": "Which control most directly supports consistent regulatory compliance?", "choices": ["Let each employee interpret rules privately", "Document policies, train employees, and monitor decisions", "Act only after a regulator complains", "Use competitor behavior as the only standard"], "correct": 1, "explanation": "Policies, training, and monitoring translate requirements into repeatable conduct and reveal problems before they grow."},
        {"text": "A lender can technically place a major fee in difficult-to-find terms. What should its manager recommend?", "choices": ["Keep it hidden because the contract is available", "Remove all written terms", "Disclose the fee prominently before agreement", "Explain the fee only after a complaint"], "correct": 2, "explanation": "Prominent advance disclosure supports informed choice and the protective intent of disclosure regulation."},
    ],
}

QUESTIONS = [
    {"question_type": "application", "question_slot": 1, "question_text": "A bank's advertisement meets the minimum font-size rule but places a required risk warning against a nearly identical background color. What should the compliance manager do?", "choices": ["Approve it because the font size is correct", "Make the warning clearly visible before publication", "Publish it and wait for complaints", "Remove every statement about risk"], "correct_index": 1, "explanation": "Making the warning visible satisfies both the written disclosure requirement and its purpose of informing customers."},
    {"question_type": "application", "question_slot": 2, "question_text": "An investment firm discovers that an automated notice technically sends on time but regularly goes to an inaccessible customer portal. Which response best reflects regulatory intent?", "choices": ["Keep the process unchanged", "Stop documenting delivery", "Redesign delivery so customers can reasonably access the notice", "Send notices only to new customers"], "correct_index": 2, "explanation": "Effective access supports the notice requirement's customer-protection purpose instead of treating delivery as a box-checking exercise."},
    {"question_type": "application", "question_slot": 3, "question_text": "A supervisor finds a legal loophole that permits a fee calculation customers are unlikely to understand. What is the strongest first step?", "choices": ["Use the loophole immediately", "Evaluate the rule's purpose and escalate the risk to compliance", "Hide the calculation from employees", "Assume competitors make the practice acceptable"], "correct_index": 1, "explanation": "Evaluating purpose and escalating the issue allows the firm to address legal, customer, and reputation risk before acting."},
    {"question_type": "application", "question_slot": 4, "question_text": "A financial services company wants evidence that employees follow both the letter and spirit of consumer-protection rules. Which practice provides the strongest evidence?", "choices": ["Rely only on employee promises", "Track complaints but never review decisions", "Document decisions, audit samples, and correct recurring problems", "Avoid written compliance standards"], "correct_index": 2, "explanation": "Documentation, testing, and corrective action demonstrate that compliance controls operate consistently in real decisions."},
]


if __name__ == "__main__":
    plan = classify_kpi(KPI_TEXT)
    clean = validate_lesson(LESSON, plan)
    assert clean["lesson_design"]["complexity"] == "standard"
    assert len(clean["practice_questions"]) == 3
    assert len(QUESTIONS) == 4
    print("Acceptance content validated: 1 lesson, 4 additional questions")

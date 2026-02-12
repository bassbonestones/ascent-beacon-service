"""Service for validating priorities against strict guidelines."""
import json
from typing import TypedDict

from app.core.llm import llm_client


class ValidationResult(TypedDict):
    """Result of priority validation."""
    is_valid: bool
    passed_rules: dict[str, bool]  # rule_name -> bool
    feedback: list[str]  # Clarifying prompts if invalid


# Example statements for each rule
RULE_EXAMPLES = {
    "personal": {
        "rule_title": "Personal experience, not abstract ideas",
        "good_examples": [
            "Because I feel more grounded and centered when I do this",
            "Because I've noticed I'm happier when I spend time on this",
            "Because this helps me feel like the parent/partner I want to be",
        ],
        "bad_examples": [
            "Because it's important",
            "Because everyone should do this",
            "Because it's good for people",
        ],
    },
    "meaning_based": {
        "rule_title": "Meaning-based, not obligation or guilt",
        "good_examples": [
            "Because this aligns with my values and how I want to live",
            "Because I've learned I regret deeply when I neglect this",
            "Because time spent here feels meaningful to me",
        ],
        "bad_examples": [
            "Because I have to",
            "Because I'll feel guilty if I don't",
            "Because it's expected of me",
        ],
    },
    "implies_protection": {
        "rule_title": "Why this needs to be protected from being crowded out",
        "good_examples": [
            "Because this gets crowded out easily but the cost of losing it is high",
            "Because neglecting this leads to stress and resentment in my life",
            "Because I know from experience that I regret it when I let this slip",
        ],
        "bad_examples": [
            "So I can finally finish it",
            "So I can prove I'm disciplined",
            "To achieve my goals",
        ],
    },
    "concrete": {
        "rule_title": "Concrete enough to guide real decisions",
        "good_examples": [
            "Because it helps me say no to work projects when they conflict",
            "Because it reminds me what to prioritize when I'm overwhelmed",
            "Because understanding this helps me make tradeoffs",
        ],
        "bad_examples": [
            "It just matters to me",
            "It's part of who I am",
            "Because I think it's important",
        ],
    },
}


async def validate_priority_name(name: str) -> ValidationResult:
    """
    Validate priority name is not generic.
    
    Generic names (❌): "Health", "Career", "Family", "Relationships"
    Specific names (✅): "Restoring physical health after burnout", 
                         "Being emotionally present for my child during early childhood"
    
    Returns:
        ValidationResult with is_valid and feedback
    """
    
    generic_terms = {
        "health", "career", "family", "relationships", "money", "finance",
        "spirituality", "spiritualself", "exercise", "work", "school", "education",
        "hobbies", "fun", "friends", "partner", "marriage", "love",
        "creativity", "art", "sports", "travel", "rest", "sleep",
    }
    
    # Quick check for obvious generics
    name_lower = name.lower().strip()
    if name_lower in generic_terms:
        return ValidationResult(
            is_valid=False,
            passed_rules={"not_generic": False},
            feedback=["That's a bit vague. Can you be more specific about what this means for you?"],
        )
    
    # Use LLM for contextual validation
    prompt = f"""
You are validating a priority name. A priority is specific enough if it goes beyond a single category word.

Too generic (single-word categories):
- "Health"
- "Career" 
- "Family"
- "Work"

Specific enough (adds meaningful context):
- "Restoring physical health after burnout"
- "Being emotionally present for my child"
- "Being emotionally present for family and friends"
- "Running 3x per week"
- "Quality time with my partner"
- "Creative projects that feel meaningful"

Priority name to evaluate: "{name}"

Is this name specific enough? Judge generously - it should fail only if it's a bare category word like "Health" or "Family".

Respond with JSON:
{{
  "is_specific": boolean,
  "reason": "brief explanation"
}}
"""
    
    try:
        response = await llm_client.chat_completion(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=150,
            response_format={"type": "json_object"},
        )
        
        content = response["choices"][0]["message"]["content"]
        result = json.loads(content)
        
        if result.get("is_specific"):
            return ValidationResult(
                is_valid=True,
                passed_rules={"not_generic": True},
                feedback=[],
            )
        else:
            return ValidationResult(
                is_valid=False,
                passed_rules={"not_generic": False},
                feedback=["Try adding a detail: instead of 'Health', say 'Fitness regimen', 'Mental health', or 'Sleep routine'"],
            )
    except Exception as e:
        print(f"Error validating priority name: {e}")
        # Fallback: check length as proxy for specificity
        if len(name.strip()) >= 12:
            return ValidationResult(
                is_valid=True,
                passed_rules={"not_generic": True},
                feedback=[],
            )
        return ValidationResult(
            is_valid=False,
            passed_rules={"not_generic": False},
            feedback=["Can you add more detail? Single words like 'Health' or 'Family' are too broad."],
        )


async def validate_why_statement(statement: str) -> ValidationResult:
    """
    Validate "why this matters" statement against 4 rules.
    
    Rule 1: Personal (references user, not abstract virtue)
    Rule 2: Meaning-based (not obligation)
    Rule 3: Implies protection (not achievement)
    Rule 4: Concrete enough to guide decisions
    
    Returns:
        ValidationResult with is_valid (all rules pass) and individual rule status
    """
    
    prompt = f"""
You are validating a priority statement that answers "Why does this matter to me?" Be GENEROUS in your evaluation. If the intent is clear and reasonable, mark it as passing.

A VALID statement meets ALL 4 of these rules:

RULE 1 - Personal, not generic (references YOUR experience or values):
✅ "Because I feel more grounded when I do this"
✅ "Because this helps me show up as the parent I want to be"
✅ "Because I care about the people in my life and want them to feel loved"
✅ "Because I want to live a long time and feel good"
❌ "Because it's important"
❌ "Because everything should be balanced"

RULE 2 - Meaning-based, not obligation (about what matters to you, not duty):
✅ "Because this aligns with how I want to live"
✅ "Because I've learned I regret neglecting this"
✅ "Because I want the people I care about to feel valued and loved"
✅ "Because I want to feel good and have energy for life"
❌ "Because I have to"
❌ "Because it's expected of me"

RULE 3 - Implies protection or prevention (protecting something important, not just achieving):
✅ "Because neglecting this consistently leads to stress and disconnection"
✅ "Because this is easy to crowd out, but costly to lose"
✅ "Because I don't want people to feel unloved or neglected by me"
✅ "Because when I neglect this, my relationships suffer"
✅ "Because without this, I lose energy and my well-being declines"
❌ "So I can finally be done with it"
❌ "So I can prove I'm disciplined"

RULE 4 - Concrete enough to guide decisions (shows impact or consequence):
✅ "Because this helps me say no to work when I need to"
✅ "Because this reminds me why I'm willing to sacrifice other things"
✅ "Because when I neglect this, people feel the impact"
✅ "Because this directly affects how I feel and show up in life"
❌ "It just matters to me"
❌ "It's part of who I am"

Statement to evaluate: "{statement}"

IMPORTANT: Be VERY generous. This is about quality of life, not perfection.
- If someone is articulating a real value (health, relationships, well-being), mark it as passing.
- "Implies protection" means protecting/preserving something important - that includes protecting your ability to feel good, have energy, or live fully.
- Only reject if the statement is truly vague (one word), purely obligation-based ("I have to"), or contradictory to the priority.

Evaluate against all 4 rules and respond with JSON:
{{
  "passes_rule_1": boolean,
  "reason_1": "brief explanation",
  "passes_rule_2": boolean,
  "reason_2": "brief explanation",
  "passes_rule_3": boolean,
  "reason_3": "brief explanation",
  "passes_rule_4": boolean,
  "reason_4": "brief explanation"
}}
"""
    
    try:
        response = await llm_client.chat_completion(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=400,
            response_format={"type": "json_object"},
        )
        
        content = response["choices"][0]["message"]["content"]
        result = json.loads(content)
        
        passed_rules = {
            "personal": result.get("passes_rule_1", False),
            "meaning_based": result.get("passes_rule_2", False),
            "implies_protection": result.get("passes_rule_3", False),
            "concrete": result.get("passes_rule_4", False),
        }
        
        all_pass = all(passed_rules.values())
        
        # Build feedback for failed rules
        feedback = []
        if not passed_rules["personal"]:
            feedback.append(result.get("reason_1", "This should reflect your personal experience, not general principles."))
        if not passed_rules["meaning_based"]:
            feedback.append(result.get("reason_2", "What meaning does this hold for you, beyond feeling obligated?"))
        if not passed_rules["implies_protection"]:
            feedback.append(result.get("reason_3", "Why does this deserve to be protected from being crowded out?"))
        if not passed_rules["concrete"]:
            feedback.append(result.get("reason_4", "Can you be more specific about how this guides your decisions?"))
        
        return ValidationResult(
            is_valid=all_pass,
            passed_rules=passed_rules,
            feedback=feedback if not all_pass else [],
        )
    
    except Exception as e:
        print(f"Error validating why statement: {e}")
        # Fallback: basic heuristic checks
        statement_lower = statement.lower()
        has_because = "because" in statement_lower or "reason" in statement_lower
        is_long_enough = len(statement.strip()) >= 20
        
        if has_because and is_long_enough:
            return ValidationResult(
                is_valid=True,
                passed_rules={
                    "personal": True,
                    "meaning_based": True,
                    "implies_protection": True,
                    "concrete": True,
                },
                feedback=[],
            )
        
        return ValidationResult(
            is_valid=False,
            passed_rules={
                "personal": has_because,
                "meaning_based": has_because,
                "implies_protection": is_long_enough,
                "concrete": is_long_enough,
            },
            feedback=["Can you tell us more about why this matters to you?"],
        )


async def validate_priority(
    name: str,
    why_statement: str,
) -> dict:
    """
    Comprehensive priority validation.
    
    Returns a dict with:
    - name_valid: bool
    - why_valid: bool  
    - name_feedback: list[str]
    - why_feedback: list[str]
    - why_passed_rules: dict[str, bool]
    - rule_examples: dict with examples for failed rules
    - overall_valid: bool (name_valid AND why_valid)
    """
    
    name_result, why_result = await asyncio.gather(
        validate_priority_name(name),
        validate_why_statement(why_statement),
    )
    
    overall_valid = name_result["is_valid"] and why_result["is_valid"]
    
    # Build rule_examples for any failed rules
    rule_examples = {}
    if not why_result["is_valid"]:
        for rule_name, passed in why_result["passed_rules"].items():
            if not passed and rule_name in RULE_EXAMPLES:
                example_data = RULE_EXAMPLES[rule_name]
                rule_examples[rule_name] = {
                    "rule_name": rule_name,
                    "rule_title": example_data["rule_title"],
                    "good_examples": example_data["good_examples"],
                    "bad_examples": example_data["bad_examples"],
                }
    
    return {
        "name_valid": name_result["is_valid"],
        "why_valid": why_result["is_valid"],
        "name_feedback": name_result["feedback"],
        "why_feedback": why_result["feedback"],
        "why_passed_rules": why_result["passed_rules"],
        "rule_examples": rule_examples if rule_examples else None,
        "overall_valid": overall_valid,
    }


# Import at end to avoid circular imports
import asyncio

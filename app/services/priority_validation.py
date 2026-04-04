"""Service for validating priorities against strict guidelines."""
import asyncio
import json
from typing import Any, TypedDict

from app.core.llm import llm_client
from app.core.logging import logger
from app.services.priority_validation_prompts import (
    RULE_EXAMPLES,
    GENERIC_TERMS,
    get_name_validation_prompt,
    get_why_validation_prompt,
)


class ValidationResult(TypedDict):
    """Result of priority validation."""
    is_valid: bool
    passed_rules: dict[str, bool]  # rule_name -> bool
    feedback: list[str]  # Clarifying prompts if invalid


async def validate_priority_name(name: str) -> ValidationResult:
    """
    Validate priority name is not generic.
    
    Generic names (❌): "Health", "Career", "Family", "Relationships"
    Specific names (✅): "Restoring physical health after burnout", 
                         "Being emotionally present for my child during early childhood"
    
    Returns:
        ValidationResult with is_valid and feedback
    """
    # Quick check for obvious generics
    name_lower = name.lower().strip()
    if name_lower in GENERIC_TERMS:
        return ValidationResult(
            is_valid=False,
            passed_rules={"not_generic": False},
            feedback=["That's a bit vague. Can you be more specific about what this means for you?"],
        )
    
    # Use LLM for contextual validation
    prompt = get_name_validation_prompt(name)
    
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
        logger.warning("Error validating priority name", error=str(e), name=name)
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
    prompt = get_why_validation_prompt(statement)
    
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
        logger.warning("Error validating why statement", error=str(e))
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
) -> dict[str, Any]:
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

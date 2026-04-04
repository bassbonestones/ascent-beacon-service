"""Constants and prompts for priority validation."""

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

GENERIC_TERMS = {
    "health", "career", "family", "relationships", "money", "finance",
    "spirituality", "spiritualself", "exercise", "work", "school", "education",
    "hobbies", "fun", "friends", "partner", "marriage", "love",
    "creativity", "art", "sports", "travel", "rest", "sleep",
}


def get_name_validation_prompt(name: str) -> str:
    """Build the LLM prompt for name validation."""
    return f"""
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


def get_why_validation_prompt(statement: str) -> str:
    """Build the LLM prompt for why statement validation."""
    return f"""
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

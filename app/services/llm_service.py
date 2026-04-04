from typing import Any

from app.core.llm import llm_client
from app.core.config import settings


# Tool definitions for function calling
VALUE_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "propose_value",
            "description": "Propose a SINGLE value statement for the user to consider. Use this only when the user has clearly articulated ONE specific thing they deeply care about and seems ready to commit to it. Never combine multiple values - only propose one at a time.",
            "parameters": {
                "type": "object",
                "properties": {
                    "statement": {
                        "type": "string",
                        "description": "A clear, specific statement of ONE value. Should describe what matters deeply to them and how it shows up in their life. Avoid using words like 'prioritize' or 'priority' - those are for later. Focus on what they VALUE and CARE ABOUT. Example: 'Being fully present with my family through deep listening and protected time together.' Keep it focused on a single core value.",
                    },
                    "rationale": {
                        "type": "string",
                        "description": "A brief, one-sentence explanation of why you're proposing this specific value based on what the user shared.",
                    },
                },
                "required": ["statement", "rationale"],
            },
        },
    }
]


class LLMService:
    """Service for LLM interactions."""
    
    @staticmethod
    async def get_recommendation(
        messages: list[dict[str, Any]],
        user_context: dict[str, Any],
    ) -> dict[str, Any]:
        """Get a structured recommendation from the LLM."""
        # Build context-specific system message
        context_mode = user_context.get("context_mode", "general")
        
        if context_mode == "values":
            system_content = """You are an assistant for Ascent Beacon, a calm intentional growth app.
Your role is to help users clarify their core values through thoughtful, exploratory conversation.

Critical Guidelines:
- Focus on ONE value at a time - never ask them to list all their values
- Ask ONE question at a time to understand what matters most to them RIGHT NOW
- Listen deeply and reflect back what you hear
- When they clearly state a value (e.g., "I value X"), recognize it and propose it - don't ask them to restate it
- NEVER output raw JSON or structured data to the user
- NEVER mention priorities or use words like "prioritize" - those come later
- Values describe what matters deeply, not what gets prioritized
- Keep responses brief and conversational (2-3 sentences max)
- Don't be pedantic or repetitive - move forward when they've expressed something clear

Process:
1. Start with how they're feeling
2. Explore ONE thing that matters to them through gentle questions
3. When they articulate a value clearly (even briefly), propose it - don't ask them to rephrase
4. Use propose_value as soon as they've expressed a clear value statement
5. After they accept/reject, move to exploring the NEXT value

If they say something like "I value personal freedom" or "Family matters to me," that's enough - propose it.
Don't ask them to restate or refine what they've already clearly expressed.

Only propose ONE value at a time. Never combine multiple values into one statement.

You are having a conversation, not conducting an interview."""
        
        elif context_mode == "priorities":
            system_content = """You are an assistant for Ascent Beacon, a calm intentional growth app.
Your role is to help users clarify their priorities through thoughtful conversation.

Guidelines:
- Ask ONE question at a time about what they want to prioritize
- Help them think about concrete goals and actions that align with their values
- NEVER output raw JSON or structured data to the user
- Keep responses conversational and supportive (2-4 sentences max)
- Guide them through defining meaningful priorities

You are having a conversation, not filling out a form."""
        
        else:
            system_content = """You are an assistant for Ascent Beacon, a calm intentional growth app.
Your role is to have supportive, thoughtful conversations with users.
Never prescribe what someone should value or prioritize.
Always maintain a gentle, supportive tone.
Keep responses conversational (2-4 sentences)."""
        
        system_message = {
            "role": "system",
            "content": system_content
        }
        
        full_messages = [system_message] + messages
        
        # Add tools if in values mode
        tools = VALUE_TOOLS if context_mode == "values" else None
        
        # Call LLM
        response = await llm_client.chat_completion(
            messages=full_messages,
            temperature=0.7,
            tools=tools,
        )
        
        return response
    
    @staticmethod
    async def get_alignment_reflection(
        declared_values: dict[str, Any],
        implied_values: dict[str, Any],
        total_variation_distance: float,
    ) -> str:
        """Get a reflection on alignment from the LLM."""
        prompt = f"""
Given the following alignment data:

Declared value weights: {declared_values}
Implied value weights (from priorities): {implied_values}
Total variation distance: {total_variation_distance:.2f}

Provide a brief, supportive reflection on the user's alignment.
Focus on coherence and clarity, not optimization.
Keep it under 3 sentences.
"""
        
        messages = [
            {
                "role": "system",
                "content": "You provide gentle, non-judgmental reflections on value alignment.",
            },
            {
                "role": "user",
                "content": prompt,
            },
        ]
        
        response = await llm_client.chat_completion(
            messages=messages,
            temperature=0.7,
            max_tokens=150,
        )
        
        return str(response["choices"][0]["message"]["content"])

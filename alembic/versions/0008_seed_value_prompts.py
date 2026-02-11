"""seed_value_prompts

Revision ID: 0008
Revises: 0007
Create Date: 2026-02-10 12:15:00.000000

"""
from typing import Sequence, Union
import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


PROMPTS = [
    # 🟦 How I show up for others (12)
    ("Being emotionally present with people I care about", "How I show up for others", 1),
    ("Listening fully without rushing to fix", "How I show up for others", 2),
    ("Showing patience when others are struggling", "How I show up for others", 3),
    ("Making time for connection even when busy", "How I show up for others", 4),
    ("Being reliable and following through", "How I show up for others", 5),
    ("Offering support without being asked", "How I show up for others", 6),
    ("Speaking honestly with care", "How I show up for others", 7),
    ("Creating a sense of safety for others", "How I show up for others", 8),
    ("Showing appreciation openly", "How I show up for others", 9),
    ("Being generous with attention", "How I show up for others", 10),
    ("Respecting others' boundaries", "How I show up for others", 11),
    ("Showing up consistently, not just intensely", "How I show up for others", 12),
    
    # 🟩 How I treat myself (12)
    ("Giving myself rest without guilt", "How I treat myself", 1),
    ("Taking care of my physical health", "How I treat myself", 2),
    ("Allowing myself to feel emotions fully", "How I treat myself", 3),
    ("Speaking to myself with kindness", "How I treat myself", 4),
    ("Protecting my energy", "How I treat myself", 5),
    ("Making space for play and joy", "How I treat myself", 6),
    ("Letting go of perfectionism", "How I treat myself", 7),
    ("Honoring my limits", "How I treat myself", 8),
    ("Taking breaks before burnout", "How I treat myself", 9),
    ("Trusting myself", "How I treat myself", 10),
    ("Being patient with my own growth", "How I treat myself", 11),
    ("Choosing self-respect over approval", "How I treat myself", 12),
    
    # 🟨 What I protect (10)
    ("My time", "What I protect", 1),
    ("My mental and emotional health", "What I protect", 2),
    ("My family's stability", "What I protect", 3),
    ("My personal boundaries", "What I protect", 4),
    ("My ability to focus deeply", "What I protect", 5),
    ("My integrity", "What I protect", 6),
    ("My home as a place of calm", "What I protect", 7),
    ("My financial security", "What I protect", 8),
    ("My autonomy", "What I protect", 9),
    ("My sense of meaning", "What I protect", 10),
    
    # 🟧 What I'm moving toward (10)
    ("Building a life that feels balanced", "What I'm moving toward", 1),
    ("Growing into a better version of myself", "What I'm moving toward", 2),
    ("Creating stability for the future", "What I'm moving toward", 3),
    ("Learning deeply and continuously", "What I'm moving toward", 4),
    ("Doing work that feels meaningful", "What I'm moving toward", 5),
    ("Becoming more present in daily life", "What I'm moving toward", 6),
    ("Living with intention rather than default", "What I'm moving toward", 7),
    ("Developing mastery in what I care about", "What I'm moving toward", 8),
    ("Creating long-term freedom", "What I'm moving toward", 9),
    ("Feeling at peace more often", "What I'm moving toward", 10),
    
    # 🟥 How I make decisions (8)
    ("Making decisions I can stand behind later", "How I make decisions", 1),
    ("Choosing long-term well-being over short-term relief", "How I make decisions", 2),
    ("Acting in alignment with my principles", "How I make decisions", 3),
    ("Pausing before reacting", "How I make decisions", 4),
    ("Being honest with myself about tradeoffs", "How I make decisions", 5),
    ("Choosing clarity over avoidance", "How I make decisions", 6),
    ("Deciding based on what truly matters", "How I make decisions", 7),
    ("Letting values guide choices, not pressure", "How I make decisions", 8),
    
    # 🟪 How I relate to the world (8)
    ("Acting with honesty even when it's uncomfortable", "How I relate to the world", 1),
    ("Treating people with fairness", "How I relate to the world", 2),
    ("Being respectful of different perspectives", "How I relate to the world", 3),
    ("Contributing positively where I can", "How I relate to the world", 4),
    ("Being mindful of my impact on others", "How I relate to the world", 5),
    ("Staying grounded in uncertainty", "How I relate to the world", 6),
    ("Acting with compassion", "How I relate to the world", 7),
    ("Being open to change", "How I relate to the world", 8),
]


def upgrade() -> None:
    value_prompts_table = sa.table(
        "value_prompts",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("prompt_text", sa.String()),
        sa.column("primary_lens", sa.String()),
        sa.column("display_order", sa.Integer()),
        sa.column("active", sa.Boolean()),
    )

    prompts_data = [
        {
            "id": uuid.uuid4(),
            "prompt_text": text,
            "primary_lens": lens,
            "display_order": order,
            "active": True,
        }
        for text, lens, order in PROMPTS
    ]

    op.bulk_insert(value_prompts_table, prompts_data)


def downgrade() -> None:
    # Delete all seeded prompts
    op.execute("DELETE FROM value_prompts")

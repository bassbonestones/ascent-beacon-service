"""Service for value operations including weight normalization."""
from decimal import Decimal
from typing import List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.value import Value, ValueRevision


async def normalize_value_weights(
    db: AsyncSession,
    user_id: str,
) -> None:
    """
    Normalize weights for all active value revisions for a user.
    
    Weights must sum to 100. This function:
    1. Gets all active value revisions for the user
    2. Sums their raw weights
    3. Calculates normalized weights that sum to 100
    4. Updates weight_normalized field
    
    Args:
        db: Database session
        user_id: User ID to normalize values for
    """
    # Get all values with their active revisions
    result = await db.execute(
        select(Value)
        .where(Value.user_id == user_id)
    )
    values = result.scalars().all()
    
    # Get active revisions
    active_revisions: List[ValueRevision] = []
    for value in values:
        if value.active_revision_id:
            revision = await db.get(ValueRevision, value.active_revision_id)
            if revision and revision.is_active:
                active_revisions.append(revision)
    
    if not active_revisions:
        return
    
    # Calculate sum of raw weights (ensure Decimal type)
    total_raw = sum((Decimal(str(r.weight_raw)) for r in active_revisions), Decimal("0"))
    
    if total_raw == 0:
        # If all weights are 0, distribute equally
        equal_weight = Decimal("100") / len(active_revisions)
        for revision in active_revisions:
            revision.weight_normalized = equal_weight
    else:
        # Normalize to sum to 100 (keep everything as Decimal)
        for revision in active_revisions:
            weight_ratio = Decimal(str(revision.weight_raw)) / total_raw
            revision.weight_normalized = weight_ratio * Decimal("100")
    
    await db.flush()


def calculate_normalized_weights(raw_weights: List[Decimal]) -> List[Decimal]:
    """
    Calculate normalized weights that sum to 100.
    
    This is a pure function for client-side calculations.
    
    Args:
        raw_weights: List of raw weight values
        
    Returns:
        List of normalized weights summing to 100
    """
    if not raw_weights:
        return []
    
    total_raw = sum(raw_weights)
    
    if total_raw == 0:
        # Equal distribution
        equal_weight = Decimal("100") / len(raw_weights)
        return [equal_weight] * len(raw_weights)
    
    # Normalize to sum to 100
    return [(w / total_raw) * Decimal("100") for w in raw_weights]


def redistribute_weight(
    current_weights: List[Decimal],
    changed_index: int,
    new_weight: Decimal,
) -> List[Decimal]:
    """
    Redistribute weights when one value changes.
    
    When a user adjusts one value's weight via slider, the remaining
    values are adjusted proportionally to maintain sum of 100.
    
    Args:
        current_weights: Current normalized weights (sum to 100)
        changed_index: Index of the weight that changed
        new_weight: New weight for the changed value
        
    Returns:
        New list of weights summing to 100
    """
    if not current_weights or changed_index >= len(current_weights):
        return current_weights
    
    new_weights = list(current_weights)
    new_weights[changed_index] = new_weight
    
    # Calculate remaining weight to distribute
    remaining = Decimal("100") - new_weight
    
    if remaining < 0:
        remaining = Decimal("0")
        new_weights[changed_index] = Decimal("100")
    
    # Get sum of other weights for proportional distribution
    other_indices = [i for i in range(len(new_weights)) if i != changed_index]
    other_sum = sum(current_weights[i] for i in other_indices)
    
    if other_sum == 0:
        # Equal distribution among others
        if other_indices:
            equal_weight = remaining / len(other_indices)
            for i in other_indices:
                new_weights[i] = equal_weight
    else:
        # Proportional distribution
        for i in other_indices:
            proportion = current_weights[i] / other_sum
            new_weights[i] = remaining * proportion
    
    return new_weights

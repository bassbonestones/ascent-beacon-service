"""
Alignment calculation helpers - pure functions for alignment calculations.

These are extracted from the alignment endpoint for testability.
"""
from decimal import Decimal
from collections import defaultdict
from typing import Any


def build_declared_distribution(values: list[Any]) -> tuple[dict[str, float], Decimal]:
    """
    Build declared value distribution from a list of values.
    
    Args:
        values: List of Value objects with active_revision_id and revisions
        
    Returns:
        Tuple of (distribution dict, total_weight)
    """
    declared: dict[str, float] = {}
    total_weight = Decimal("0")
    
    for value in values:
        if value.active_revision_id:
            active_rev = next(
                (r for r in value.revisions if r.id == value.active_revision_id),
                None
            )
            if active_rev:
                declared[active_rev.id] = float(active_rev.weight_raw)
                total_weight += active_rev.weight_raw
    
    return declared, total_weight


def normalize_weights(weights: dict[str, float], total: float) -> dict[str, float]:
    """
    Normalize weights to sum to 1.0.
    
    Args:
        weights: Dict of id -> weight
        total: Total weight sum
        
    Returns:
        Normalized dict with same keys
    """
    if total > 0:
        return {k: v / total for k, v in weights.items()}
    return weights.copy()


def build_implied_distribution(priorities: list[Any]) -> dict[str, float]:
    """
    Build implied value distribution from anchored priorities.
    
    Args:
        priorities: List of Priority objects with active revisions and value_links
        
    Returns:
        Dict of value_revision_id -> implied weight
    """
    implied_weights: dict[str, float] = defaultdict(float)
    
    for priority in priorities:
        if priority.active_revision_id:
            priority_rev = next(
                (r for r in priority.revisions if r.id == priority.active_revision_id),
                None
            )
            if priority_rev and priority_rev.is_anchored:
                # Distribute priority score across linked values
                total_link_weight = sum(
                    float(link.link_weight) for link in priority_rev.value_links
                )
                
                if total_link_weight > 0:
                    for link in priority_rev.value_links:
                        contribution = (
                            float(priority_rev.score)
                            * float(link.link_weight)
                            / total_link_weight
                        )
                        implied_weights[link.value_revision_id] += contribution
    
    return dict(implied_weights)


def compute_total_variation_distance(
    declared: dict[str, float],
    implied: dict[str, float],
) -> float:
    """
    Compute Total Variation Distance (TVD) between two distributions.
    
    TVD = (1/2) * sum(|p(x) - q(x)|) for all x
    
    Args:
        declared: Declared value distribution (normalized)
        implied: Implied value distribution (normalized)
        
    Returns:
        TVD value between 0 and 1
    """
    all_keys = set(declared.keys()) | set(implied.keys())
    tvd = sum(
        abs(declared.get(k, 0.0) - implied.get(k, 0.0))
        for k in all_keys
    ) / 2.0
    return tvd


def compute_alignment_fit(tvd: float) -> float:
    """
    Compute alignment fit from TVD.
    
    Alignment fit = 1 - TVD
    
    Args:
        tvd: Total variation distance
        
    Returns:
        Alignment fit between 0 and 1
    """
    return 1.0 - tvd

from pydantic import BaseModel


class AlignmentCheckResponse(BaseModel):
    declared: dict[str, float]  # value_revision_id -> weight
    implied: dict[str, float]   # value_revision_id -> weight
    total_variation_distance: float
    alignment_fit: float
    reflection: str

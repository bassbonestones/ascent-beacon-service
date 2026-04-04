from decimal import Decimal
from datetime import datetime
from pydantic import BaseModel


class PriorityValueLinkInput(BaseModel):
    value_revision_id: str
    link_weight: Decimal = Decimal("1.0")


class SetLinksRequest(BaseModel):
    links: list[PriorityValueLinkInput]


class PriorityValueLinkResponse(BaseModel):
    id: str
    priority_revision_id: str
    value_revision_id: str
    value_id: str | None = None
    link_weight: Decimal
    created_at: datetime
    
    model_config = {"from_attributes": True}


class LinksResponse(BaseModel):
    links: list[PriorityValueLinkResponse]

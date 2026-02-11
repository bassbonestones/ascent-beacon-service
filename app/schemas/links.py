from decimal import Decimal
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
    link_weight: Decimal
    created_at: str
    
    model_config = {"from_attributes": True}


class LinksResponse(BaseModel):
    links: list[PriorityValueLinkResponse]

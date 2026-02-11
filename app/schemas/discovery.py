from pydantic import BaseModel
from typing import Optional
from uuid import UUID


class ValuePromptResponse(BaseModel):
    """A curated value discovery prompt."""
    id: UUID
    prompt_text: str
    primary_lens: str
    display_order: int
    active: bool

    class Config:
        from_attributes = True


class UserValueSelectionBase(BaseModel):
    """Base schema for value selection."""
    prompt_id: UUID
    bucket: str  # 'core', 'important', 'not_now'
    display_order: int = 0
    custom_text: Optional[str] = None


class UserValueSelectionCreate(UserValueSelectionBase):
    """Create a new value selection."""
    pass


class UserValueSelectionUpdate(BaseModel):
    """Update an existing value selection."""
    bucket: Optional[str] = None
    display_order: Optional[int] = None


class UserValueSelectionResponse(BaseModel):
    """Value selection with prompt details."""
    id: UUID
    user_id: UUID
    prompt_id: UUID
    bucket: str
    display_order: int
    custom_text: Optional[str]
    prompt: ValuePromptResponse

    class Config:
        from_attributes = True


class DiscoveryPromptsResponse(BaseModel):
    """All prompts grouped by lens."""
    prompts: list[ValuePromptResponse]


class UserSelectionsResponse(BaseModel):
    """User's selections grouped by bucket."""
    selections: list[UserValueSelectionResponse]
    
    
class BulkSelectionsUpdate(BaseModel):
    """Bulk update selections."""
    selections: list[UserValueSelectionBase]

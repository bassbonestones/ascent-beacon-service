from pydantic import BaseModel


class MessageResponse(BaseModel):
    message: str


class SuccessResponse(BaseModel):
    ok: bool = True

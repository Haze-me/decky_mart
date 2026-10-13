from pydantic import BaseModel

from app.models.reaction import ReactionType


class ReactionRequest(BaseModel):
    reaction_type: ReactionType


class ReactionResponse(BaseModel):
    my_reaction: ReactionType | None
    reaction_count: int
    reaction_breakdown: dict[str, int]

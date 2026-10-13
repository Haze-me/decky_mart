from pydantic import BaseModel


class CSRFResponse(BaseModel):
    detail: str

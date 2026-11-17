from pydantic import BaseModel


class CategoryItem(BaseModel):
    slug: str
    name: str


class CategoryListResponse(BaseModel):
    items: list[CategoryItem]

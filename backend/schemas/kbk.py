"""KBK search schemas."""

from typing import List

from pydantic import BaseModel


class KBKEntry(BaseModel):
    code: str
    short_name: str
    description: str
    kvr: str


class KBKSearchResponse(BaseModel):
    results: List[KBKEntry]
    count: int

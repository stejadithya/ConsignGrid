from dataclasses import asdict
from datetime import date, datetime

from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.modules.identity.deps import DB, CurrentUser
from app.modules.search import service

router = APIRouter(tags=["search"])


class HitOut(BaseModel):
    type: str
    label: str
    id: int
    title: str
    subtitle: str | None
    status: str | None
    when: date | datetime | None
    href: str
    exact: bool = False


class SearchOut(BaseModel):
    query: str
    documents: list[HitOut]
    dealers: list[HitOut]
    tyres: list[HitOut]
    people: list[HitOut]


@router.get("/search", response_model=SearchOut)
def search(db: DB, user: CurrentUser, q: str = Query(default="", max_length=100)):
    """One search box: documents by number, dealers, tyres and people, a few of each, scoped to what you can open."""
    return SearchOut(**asdict(service.search(db, user, q)))

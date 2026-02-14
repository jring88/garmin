from datetime import datetime

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select

from app.database import async_session
from app.models import Journal
from app.schemas import JournalCreate, JournalOut, JournalUpdate

router = APIRouter(tags=["journal"])


@router.get("/journal", response_model=list[JournalOut])
async def list_journal(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    category: str | None = None,
):
    query = select(Journal).order_by(Journal.entry_date.desc()).limit(limit).offset(offset)
    if category:
        query = query.where(Journal.category == category)

    async with async_session() as session:
        result = await session.execute(query)
        return [JournalOut.model_validate(j) for j in result.scalars().all()]


@router.post("/journal", response_model=JournalOut)
async def create_journal(entry: JournalCreate):
    journal = Journal(
        entry_date=entry.entry_date,
        category=entry.category,
        content=entry.content,
        rating=entry.rating,
        tags=entry.tags,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    async with async_session() as session:
        session.add(journal)
        await session.commit()
        await session.refresh(journal)
        return JournalOut.model_validate(journal)


@router.put("/journal/{journal_id}", response_model=JournalOut)
async def update_journal(journal_id: int, updates: JournalUpdate):
    async with async_session() as session:
        journal = await session.get(Journal, journal_id)
        if not journal:
            raise HTTPException(status_code=404, detail="Journal entry not found")

        for field, value in updates.model_dump(exclude_unset=True).items():
            setattr(journal, field, value)
        journal.updated_at = datetime.utcnow()

        await session.commit()
        await session.refresh(journal)
        return JournalOut.model_validate(journal)


@router.delete("/journal/{journal_id}")
async def delete_journal(journal_id: int):
    async with async_session() as session:
        journal = await session.get(Journal, journal_id)
        if not journal:
            raise HTTPException(status_code=404, detail="Journal entry not found")
        await session.delete(journal)
        await session.commit()
        return {"message": "Deleted"}

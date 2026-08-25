"""SQLAlchemy ORM models for short-term memory / metadata: one row per
task run, one row per individual agent turn within that task. Backed by
SQLite by default (swap sqlite_path for a real DATABASE_URL to point at
Postgres instead — this file doesn't hardcode SQLite anywhere except the
default connection string).

This is the structured, queryable counterpart to VectorMemory: "what did
we run and when, with what result" belongs here; "find me something
semantically similar to X" belongs in vector_store.py.
"""
from __future__ import annotations

import time
from typing import Optional

from sqlalchemy import create_engine, Column, Integer, String, Float, Boolean, Text, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

Base = declarative_base()


class TaskRecord(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_text = Column(Text, nullable=False)
    target_context = Column(Text, default="")     # JSON-serialized dict
    status = Column(String(20), default="running")  # running | done | failed
    final_answer = Column(Text, default="")
    total_steps = Column(Integer, default=0)
    created_at = Column(Float, default=time.time)
    completed_at = Column(Float, nullable=True)

    turns = relationship("AgentTurnRecord", back_populates="task", cascade="all, delete-orphan")


class AgentTurnRecord(Base):
    __tablename__ = "agent_turns"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=False)
    agent_name = Column(String(20), nullable=False)
    model = Column(String(50), nullable=False)
    prompt_excerpt = Column(Text, default="")
    response_excerpt = Column(Text, default="")
    latency_s = Column(Float, default=0.0)
    mocked = Column(Boolean, default=False)
    created_at = Column(Float, default=time.time)

    task = relationship("TaskRecord", back_populates="turns")


class MetadataStore:
    def __init__(self, db_path: str):
        import os
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        self.engine = create_engine(f"sqlite:///{db_path}", future=True)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, future=True)

    def record_task_start(self, task_text: str, target_context: Optional[dict] = None) -> int:
        import json
        with self.Session() as session:
            record = TaskRecord(
                task_text=task_text,
                target_context=json.dumps(target_context or {}),
                status="running",
            )
            session.add(record)
            session.commit()
            return record.id

    def record_turn(self, task_id: int, agent_name: str, model: str, prompt: str,
                    response: str, latency_s: float, mocked: bool):
        with self.Session() as session:
            turn = AgentTurnRecord(
                task_id=task_id, agent_name=agent_name, model=model,
                prompt_excerpt=prompt[:500], response_excerpt=response[:500],
                latency_s=latency_s, mocked=mocked,
            )
            session.add(turn)
            session.commit()

    def record_task_end(self, task_id: int, status: str, final_answer: str, total_steps: int):
        with self.Session() as session:
            record = session.get(TaskRecord, task_id)
            if record is None:
                return
            record.status = status
            record.final_answer = final_answer[:2000]
            record.total_steps = total_steps
            record.completed_at = time.time()
            session.commit()

    def get_task(self, task_id: int) -> Optional[dict]:
        with self.Session() as session:
            record = session.get(TaskRecord, task_id)
            if record is None:
                return None
            return {
                "id": record.id, "task_text": record.task_text, "status": record.status,
                "final_answer": record.final_answer, "total_steps": record.total_steps,
                "created_at": record.created_at, "completed_at": record.completed_at,
                "turns": [
                    {"agent": t.agent_name, "model": t.model, "latency_s": t.latency_s, "mocked": t.mocked}
                    for t in record.turns
                ],
            }

    def recent_tasks(self, limit: int = 20) -> list[dict]:
        with self.Session() as session:
            records = session.query(TaskRecord).order_by(TaskRecord.created_at.desc()).limit(limit).all()
            return [{"id": r.id, "task_text": r.task_text, "status": r.status,
                    "created_at": r.created_at} for r in records]

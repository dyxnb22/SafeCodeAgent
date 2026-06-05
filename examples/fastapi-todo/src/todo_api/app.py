"""Small FastAPI todo API used by the SafeCode Agent demo."""

from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel, Field

from todo_api.store import store

app = FastAPI(title="SafeCode Todo API")


class TodoCreate(BaseModel):
    """Input payload for creating a todo."""

    title: str = Field(min_length=1, max_length=120)
    completed: bool = False


@app.get("/todos")
def list_todos() -> list[dict[str, int | str | bool]]:
    """Return all todos."""
    return store.list_todos()


@app.post("/todos", status_code=201)
def create_todo(payload: TodoCreate) -> dict[str, int | str | bool]:
    """Create one todo."""
    return store.create(title=payload.title, completed=payload.completed)

"""Small API facade used by the realistic demo tests."""

from __future__ import annotations

from todo_service.store import TodoStore


class TodoAPI:
    """Application-facing facade over TodoStore."""

    def __init__(self, store: TodoStore | None = None) -> None:
        self.store = store or TodoStore()

    def create_todo(self, title: str) -> dict:
        item = self.store.add(title)
        return {"id": item.id, "title": item.title, "completed": item.completed}

    def complete_todo(self, todo_id: int) -> dict:
        item = self.store.complete(todo_id)
        return {"id": item.id, "title": item.title, "completed": item.completed}

    def list_open_todos(self) -> list[dict]:
        return [
            {"id": item.id, "title": item.title, "completed": item.completed}
            for item in self.store.list_open()
        ]

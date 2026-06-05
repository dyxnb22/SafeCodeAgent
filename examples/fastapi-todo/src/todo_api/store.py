"""In-memory todo store for the FastAPI demo."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Todo:
    """One todo item."""

    id: int
    title: str
    completed: bool = False

    def as_dict(self) -> dict[str, int | str | bool]:
        return {"id": self.id, "title": self.title, "completed": self.completed}


class TodoStore:
    """Tiny in-memory store with deterministic ids."""

    def __init__(self) -> None:
        self._items: dict[int, Todo] = {}
        self._next_id = 1

    def reset(self) -> None:
        self._items.clear()
        self._next_id = 1

    def list_todos(self) -> list[dict[str, int | str | bool]]:
        return [todo.as_dict() for todo in self._items.values()]

    def create(self, title: str, completed: bool = False) -> dict[str, int | str | bool]:
        todo = Todo(id=self._next_id, title=title, completed=completed)
        self._items[todo.id] = todo
        self._next_id += 1
        return todo.as_dict()


store = TodoStore()

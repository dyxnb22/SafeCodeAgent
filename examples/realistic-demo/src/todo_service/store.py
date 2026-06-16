"""In-memory todo store for the realistic SafeCode demo."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Todo:
    id: int
    title: str
    completed: bool


class TodoStore:
    """Tiny in-memory store."""

    def __init__(self) -> None:
        self._items: list[Todo] = []
        self._next_id = 1

    def add(self, title: str) -> Todo:
        item = Todo(id=self._next_id, title=title, completed=True)
        self._next_id += 1
        self._items.append(item)
        return item

    def complete(self, todo_id: int) -> Todo:
        for item in self._items:
            if item.id == todo_id:
                item.completed = True
                return item
        raise KeyError(todo_id)

    def list_open(self) -> list[Todo]:
        return list(self._items)

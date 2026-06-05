from fastapi.testclient import TestClient

from todo_api.app import app
from todo_api.store import store


def client() -> TestClient:
    store.reset()
    return TestClient(app)


def test_get_todos_starts_empty():
    response = client().get("/todos")

    assert response.status_code == 200
    assert response.json() == []


def test_post_todo_creates_item():
    response = client().post("/todos", json={"title": "write baseline tests"})

    assert response.status_code == 201
    assert response.json() == {"id": 1, "title": "write baseline tests", "completed": False}


def test_get_todos_returns_created_items():
    api = client()
    api.post("/todos", json={"title": "first"})
    api.post("/todos", json={"title": "second", "completed": True})

    assert api.get("/todos").json() == [
        {"id": 1, "title": "first", "completed": False},
        {"id": 2, "title": "second", "completed": True},
    ]


def test_post_todo_rejects_blank_title():
    response = client().post("/todos", json={"title": ""})

    assert response.status_code == 422

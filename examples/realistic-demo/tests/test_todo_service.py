from todo_service.api import TodoAPI


def test_new_todo_is_open_by_default():
    api = TodoAPI()

    todo = api.create_todo("write portfolio demo")

    assert todo["completed"] is False


def test_list_open_todos_excludes_completed_items():
    api = TodoAPI()
    first = api.create_todo("ship v6")
    second = api.create_todo("record demo")

    api.complete_todo(first["id"])

    open_items = api.list_open_todos()
    assert [item["id"] for item in open_items] == [second["id"]]
    assert all(item["completed"] is False for item in open_items)

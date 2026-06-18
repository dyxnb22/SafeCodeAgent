"""Sample application module for enterprise RAG fixtures."""


def fetch_user(user_id: str) -> dict[str, str]:
    """Fetch a user record by identifier."""
    return {"id": user_id, "name": "example"}


class UserRepository:
    """In-memory user repository."""

    def list_users(self) -> list[dict[str, str]]:
        return [{"id": "1", "name": "alice"}]

def fetch_user(user_id: str):
    query = f"SELECT * FROM users WHERE id={user_id}"
    return db.execute(query)

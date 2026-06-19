from pathlib import Path

BASE_DIR = Path("/var/data")


def read_user_file(path: str) -> str:
    return open(path).read()

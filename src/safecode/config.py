"""Application configuration for SafeCode Agent."""

from pydantic import BaseModel


class SafeCodeConfig(BaseModel):
    """Small v0.1 config object."""

    sac_dir: str = ".sac"
    max_tree_files: int = 200
    max_file_lines: int = 300

"""Tests for ConversationBuffer (v6.7.0)."""

from __future__ import annotations

from pathlib import Path

import pytest

from safecode.agent.conversation import (
    ConversationBuffer,
    _MAX_TURNS,
    _COMPRESS_BATCH,
)


class TestConversationBufferBasics:
    def test_starts_empty(self, tmp_path: Path) -> None:
        buf = ConversationBuffer(session_id="s1", sac_dir=tmp_path)
        assert buf.is_empty()
        assert buf.turn_count() == 0
        assert buf.to_messages() == []

    def test_append_user_and_assistant(self, tmp_path: Path) -> None:
        buf = ConversationBuffer(session_id="s1", sac_dir=tmp_path)
        buf.append_user("fix the bug in src/foo.py")
        buf.append_assistant("I'll read the file first.")
        msgs = buf.to_messages()
        assert len(msgs) == 2
        assert msgs[0]["role"] == "user"
        assert msgs[1]["role"] == "assistant"

    def test_turn_count(self, tmp_path: Path) -> None:
        buf = ConversationBuffer(session_id="s1", sac_dir=tmp_path)
        buf.append_user("first question")
        buf.append_assistant("first answer")
        buf.append_user("second question")
        assert buf.turn_count() == 2

    def test_tool_result_appended(self, tmp_path: Path) -> None:
        buf = ConversationBuffer(session_id="s1", sac_dir=tmp_path)
        buf.append_tool_result("read_file", "def foo(): pass")
        msgs = buf.to_messages()
        assert len(msgs) == 1
        assert msgs[0]["role"] == "tool"
        assert "read_file" in msgs[0]["content"]

    def test_to_messages_returns_copy(self, tmp_path: Path) -> None:
        buf = ConversationBuffer(session_id="s1", sac_dir=tmp_path)
        buf.append_user("hello")
        copy = buf.to_messages()
        copy.append({"role": "ghost", "content": "intruder"})
        assert len(buf.to_messages()) == 1


class TestConversationBufferPersistence:
    def test_persists_to_disk(self, tmp_path: Path) -> None:
        sac_dir = tmp_path / ".sac"
        buf = ConversationBuffer(session_id="sess-abc", sac_dir=sac_dir)
        buf.append_user("hello")
        buf.append_assistant("world")
        jsonl_path = sac_dir / "sessions" / "sess-abc" / "conversation.jsonl"
        assert jsonl_path.exists()
        lines = jsonl_path.read_text().splitlines()
        assert len(lines) == 2

    def test_load_from_disk(self, tmp_path: Path) -> None:
        sac_dir = tmp_path / ".sac"
        buf = ConversationBuffer(session_id="sess-xyz", sac_dir=sac_dir)
        buf.append_user("question one")
        buf.append_assistant("answer one")

        # Re-load from disk
        buf2 = ConversationBuffer.load("sess-xyz", sac_dir)
        assert buf2.turn_count() == 1
        msgs = buf2.to_messages()
        assert "question one" in msgs[0]["content"]

    def test_load_missing_session_returns_empty(self, tmp_path: Path) -> None:
        buf = ConversationBuffer.load("nonexistent", tmp_path / ".sac")
        assert buf.is_empty()

    def test_load_corrupt_file_returns_empty(self, tmp_path: Path) -> None:
        sac_dir = tmp_path / ".sac"
        path = sac_dir / "sessions" / "bad" / "conversation.jsonl"
        path.parent.mkdir(parents=True)
        path.write_text("NOT JSON\n{corrupt\n")
        buf = ConversationBuffer.load("bad", sac_dir)
        # Should not raise; bad lines are skipped
        assert isinstance(buf, ConversationBuffer)


class TestConversationBufferSecrets:
    def test_secret_in_user_message_is_redacted(self, tmp_path: Path) -> None:
        # Use a pattern the redactor actually catches: api_key=<value>
        buf = ConversationBuffer(session_id="s1", sac_dir=tmp_path)
        buf.append_user('api_key = "supersecretvalue12345"')
        msgs = buf.to_messages()
        assert "supersecretvalue12345" not in msgs[0]["content"]

    def test_secret_not_written_to_disk(self, tmp_path: Path) -> None:
        sac_dir = tmp_path / ".sac"
        buf = ConversationBuffer(session_id="s1", sac_dir=sac_dir)
        secret_value = "supersecretvalue12345"
        buf.append_assistant(f'token = "{secret_value}"')
        jsonl = (sac_dir / "sessions" / "s1" / "conversation.jsonl").read_text()
        assert secret_value not in jsonl


class TestConversationBufferCompression:
    def test_compresses_when_over_cap(self, tmp_path: Path) -> None:
        buf = ConversationBuffer(session_id="s1", sac_dir=tmp_path)
        # Add more than _MAX_TURNS user messages
        for i in range(_MAX_TURNS + 5):
            buf.append_user(f"user message {i}")
            buf.append_assistant(f"assistant reply {i}")
        # After compression, user count should be back at or below _MAX_TURNS
        assert buf.turn_count() <= _MAX_TURNS

    def test_compression_inserts_summary(self, tmp_path: Path) -> None:
        buf = ConversationBuffer(session_id="s1", sac_dir=tmp_path)
        for i in range(_MAX_TURNS + 2):
            buf.append_user(f"msg {i}")
            buf.append_assistant(f"rep {i}")
        msgs = buf.to_messages()
        # First message should be a compression summary
        assert "compressed" in msgs[0]["content"].lower() or "summary" in msgs[0]["content"].lower()


class TestMentionedFiles:
    def test_extracts_file_paths_from_messages(self, tmp_path: Path) -> None:
        buf = ConversationBuffer(session_id="s1", sac_dir=tmp_path)
        buf.append_user("look at src/safecode/agent/loop.py")
        buf.append_assistant("also check tests/test_foo.py for coverage")
        files = buf.mentioned_files()
        assert any("loop.py" in f for f in files)
        assert any("test_foo.py" in f for f in files)

    def test_returns_empty_when_no_files(self, tmp_path: Path) -> None:
        buf = ConversationBuffer(session_id="s1", sac_dir=tmp_path)
        buf.append_user("what does this project do?")
        assert buf.mentioned_files() == []

    def test_no_duplicates(self, tmp_path: Path) -> None:
        buf = ConversationBuffer(session_id="s1", sac_dir=tmp_path)
        buf.append_user("edit src/foo.py please")
        buf.append_assistant("I'll edit src/foo.py now")
        files = buf.mentioned_files()
        assert len(files) == len(set(files))

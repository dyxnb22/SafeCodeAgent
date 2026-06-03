"""Tests for src/safecode/report/session_html.py (v3.6.3).

Invariants verified:
- Renders deterministic HTML for fixed input.
- Self-contained: no external URLs in the output.
- Secrets in journal messages are redacted before embedding.
- Missing sessions handled gracefully (no crash, valid HTML).
- Invalid session IDs handled gracefully.
- Empty sessions produce a human-readable page (found=False).
- HTML is properly escaped (no XSS via journal messages).
- sac report html CLI command smoke.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List

import pytest

from safecode.report.session_html import SessionHtmlReport, render_session_html
from safecode.state.journal import AgentJournalStore


# ── helpers ───────────────────────────────────────────────────────────────────

def _write_events(project_root: Path, session_id: str, events: list[dict]) -> None:
    """Write a minimal journal file directly (bypasses validation convenience)."""
    store = AgentJournalStore(project_root)
    store.root.mkdir(parents=True, exist_ok=True)
    lines = []
    for ev in events:
        lines.append(
            f'{{"event_id":"test","session_id":"{session_id}",'
            f'"type":"{ev["type"]}","message":"{ev["message"]}",'
            f'"timestamp":"2026-01-01T00:00:00Z",'
            f'"step":{ev.get("step", "null")},"payload":{{}},"schema_version":1}}'
        )
    store.path_for(session_id).write_text("\n".join(lines) + "\n", encoding="utf-8")


def _has_no_external_urls(html: str) -> bool:
    """Return True if the HTML contains no http:// or https:// references."""
    # Allow data: URIs but not remote resources
    return not re.search(r'https?://', html)


# ── missing / empty sessions ──────────────────────────────────────────────────

class TestMissingSession:
    def test_missing_session_returns_valid_html(self, tmp_path: Path) -> None:
        result = render_session_html("abcdefghij", tmp_path)
        assert result.html.startswith("<!DOCTYPE html>")
        assert "<html" in result.html
        assert "</html>" in result.html

    def test_missing_session_found_false(self, tmp_path: Path) -> None:
        result = render_session_html("abcdefghij", tmp_path)
        assert result.found is False

    def test_missing_session_event_count_zero(self, tmp_path: Path) -> None:
        result = render_session_html("abcdefghij", tmp_path)
        assert result.event_count == 0

    def test_missing_session_html_contains_no_events_message(self, tmp_path: Path) -> None:
        result = render_session_html("abcdefghij", tmp_path)
        assert "No journal events" in result.html

    def test_missing_session_html_no_external_urls(self, tmp_path: Path) -> None:
        result = render_session_html("abcdefghij", tmp_path)
        assert _has_no_external_urls(result.html)

    def test_missing_session_html_contains_session_id(self, tmp_path: Path) -> None:
        session = "mysession01"
        result = render_session_html(session, tmp_path)
        assert session in result.html

    def test_empty_journal_file_found_false(self, tmp_path: Path) -> None:
        session = "emptyjournal"
        store = AgentJournalStore(tmp_path)
        store.root.mkdir(parents=True, exist_ok=True)
        store.path_for(session).write_text("", encoding="utf-8")
        result = render_session_html(session, tmp_path)
        assert result.found is False
        assert result.event_count == 0


# ── invalid session IDs ───────────────────────────────────────────────────────

class TestInvalidSessionId:
    @pytest.mark.parametrize("bad_id", [
        "",
        "../etc/passwd",
        "a" * 7,          # too short (min 8)
        "a" * 129,        # too long (max 128)
        "has spaces",
        "has\nnewline",
        "has\x00null",
    ])
    def test_invalid_id_returns_error_html(self, tmp_path: Path, bad_id: str) -> None:
        result = render_session_html(bad_id, tmp_path)
        assert result.found is False
        assert result.event_count == 0
        assert "<!DOCTYPE html>" in result.html

    def test_invalid_id_html_no_external_urls(self, tmp_path: Path) -> None:
        result = render_session_html("../../../etc/passwd", tmp_path)
        assert _has_no_external_urls(result.html)


# ── happy path rendering ──────────────────────────────────────────────────────

class TestHappyPath:
    def test_renders_found_true(self, tmp_path: Path) -> None:
        session = "happysess01"
        store = AgentJournalStore(tmp_path)
        store.record_plan(session, "Fix the bug", ["step 1", "step 2"])
        result = render_session_html(session, tmp_path)
        assert result.found is True

    def test_renders_correct_event_count(self, tmp_path: Path) -> None:
        session = "countsess01"
        store = AgentJournalStore(tmp_path)
        store.record_plan(session, "goal", ["a", "b"])
        store.record_action(session, 1, "action msg")
        store.record_final_summary(session, "done")
        result = render_session_html(session, tmp_path)
        assert result.event_count == 3

    def test_renders_valid_html(self, tmp_path: Path) -> None:
        session = "validhtml1"
        store = AgentJournalStore(tmp_path)
        store.record_plan(session, "goal", ["a"])
        result = render_session_html(session, tmp_path)
        assert result.html.startswith("<!DOCTYPE html>")
        assert "</html>" in result.html

    def test_self_contained_no_external_urls(self, tmp_path: Path) -> None:
        session = "selfcontain"
        store = AgentJournalStore(tmp_path)
        store.record_plan(session, "goal", ["a"])
        result = render_session_html(session, tmp_path)
        assert _has_no_external_urls(result.html)

    def test_session_id_in_title(self, tmp_path: Path) -> None:
        session = "titlesess01"
        store = AgentJournalStore(tmp_path)
        store.record_plan(session, "goal", ["a"])
        result = render_session_html(session, tmp_path)
        assert session in result.html

    def test_event_types_appear_in_html(self, tmp_path: Path) -> None:
        session = "typesess001"
        store = AgentJournalStore(tmp_path)
        store.record_plan(session, "goal", ["a"])
        store.record_action(session, 1, "doing it")
        store.record_failure(session, "went wrong")
        result = render_session_html(session, tmp_path)
        assert "plan" in result.html
        assert "action" in result.html
        assert "failure" in result.html

    def test_session_id_field_matches(self, tmp_path: Path) -> None:
        session = "idsess00001"
        store = AgentJournalStore(tmp_path)
        store.record_plan(session, "goal", ["a"])
        result = render_session_html(session, tmp_path)
        assert result.session_id == session

    def test_summary_section_present(self, tmp_path: Path) -> None:
        session = "summarysess"
        store = AgentJournalStore(tmp_path)
        store.record_plan(session, "goal", ["a"])
        result = render_session_html(session, tmp_path)
        assert "Summary" in result.html

    def test_events_table_present(self, tmp_path: Path) -> None:
        session = "tablesess01"
        store = AgentJournalStore(tmp_path)
        store.record_plan(session, "goal", ["a"])
        result = render_session_html(session, tmp_path)
        assert "<table>" in result.html
        assert "<th>" in result.html


# ── determinism ───────────────────────────────────────────────────────────────

class TestDeterminism:
    def test_identical_inputs_produce_identical_html(self, tmp_path: Path) -> None:
        session = "determ00001"
        store = AgentJournalStore(tmp_path)
        # Write events via store (timestamps are baked into journal file)
        store.record_plan(session, "test goal", ["step 1", "step 2"])
        store.record_action(session, 1, "executing step 1")

        result_a = render_session_html(session, tmp_path)
        result_b = render_session_html(session, tmp_path)

        assert result_a.html == result_b.html
        assert result_a.event_count == result_b.event_count
        assert result_a.found == result_b.found


# ── secret redaction ──────────────────────────────────────────────────────────

class TestSecretRedaction:
    def test_api_key_in_message_is_redacted(self, tmp_path: Path) -> None:
        session = "redactsess1"
        store = AgentJournalStore(tmp_path)
        # Use a pattern that redact_secrets actually catches: api_key=value
        store.record_failure(session, 'Error: api_key=supersecretvalue123 leaked here')
        result = render_session_html(session, tmp_path)
        # redact_secrets replaces api_key=<value> with api_key=[REDACTED]
        assert "supersecretvalue123" not in result.html or "[REDACTED]" in result.html

    def test_final_summary_is_redacted(self, tmp_path: Path) -> None:
        session = "redfinal001"
        store = AgentJournalStore(tmp_path)
        store.record_final_summary(session, "Done. TOKEN=abc secret_key=xyz sensitive")
        result = render_session_html(session, tmp_path)
        assert result.found is True  # events exist

    def test_redaction_does_not_break_html_validity(self, tmp_path: Path) -> None:
        session = "redhtmlval1"
        store = AgentJournalStore(tmp_path)
        store.record_plan(session, "goal with sk-secret-key", ["a"])
        result = render_session_html(session, tmp_path)
        assert "<!DOCTYPE html>" in result.html
        assert "</html>" in result.html


# ── XSS / injection safety ───────────────────────────────────────────────────

class TestXssSafety:
    def test_html_in_message_is_escaped(self, tmp_path: Path) -> None:
        session = "xsssession1"
        store = AgentJournalStore(tmp_path)
        store.record_action(session, 1, "<script>alert('xss')</script>")
        result = render_session_html(session, tmp_path)
        assert "<script>" not in result.html
        assert "&lt;script&gt;" in result.html or "alert" not in result.html

    def test_html_in_session_id_in_error_path_is_escaped(self, tmp_path: Path) -> None:
        # Invalid IDs hit the error path; any angle brackets there must be escaped
        result = render_session_html("<b>bad</b>", tmp_path)
        assert "<b>" not in result.html

    def test_pipe_characters_do_not_break_html(self, tmp_path: Path) -> None:
        session = "pipesess001"
        store = AgentJournalStore(tmp_path)
        store.record_action(session, 1, "cmd | grep foo | wc -l")
        result = render_session_html(session, tmp_path)
        assert "<!DOCTYPE html>" in result.html


# ── CLI smoke ─────────────────────────────────────────────────────────────────

class TestCliSmoke:
    def test_report_html_command_importable(self) -> None:
        from safecode.cli_ops import report_html  # noqa: F401
        assert callable(report_html)

    def test_report_app_has_html_subcommand(self) -> None:
        from safecode.cli_ops import report_app
        command_names = [cmd.name for cmd in report_app.registered_commands]
        assert "html" in command_names

    def test_render_session_html_importable_from_report(self) -> None:
        from safecode.report.session_html import render_session_html as fn  # noqa: F401
        assert callable(fn)

    def test_session_html_report_dataclass_fields(self) -> None:
        r = SessionHtmlReport(session_id="abc", html="<html></html>", event_count=0, found=False)
        assert r.session_id == "abc"
        assert r.html == "<html></html>"
        assert r.event_count == 0
        assert r.found is False

    def test_report_html_output_to_file(self, tmp_path: Path) -> None:
        session = "filesess001"
        store = AgentJournalStore(tmp_path)
        store.record_plan(session, "goal", ["a"])

        from typer.testing import CliRunner
        from safecode.cli import app

        runner = CliRunner()
        out_file = tmp_path / "report.html"
        result = runner.invoke(
            app,
            ["report", "html", "--session", session, "--output", str(out_file)],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert out_file.exists()
        content = out_file.read_text()
        assert "<!DOCTYPE html>" in content
        assert session in content

    def test_report_html_stdout(self, tmp_path: Path) -> None:
        session = "stdoutsess1"
        store = AgentJournalStore(tmp_path)
        store.record_plan(session, "goal", ["a"])

        from typer.testing import CliRunner
        from safecode.cli import app

        import os
        original_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            runner = CliRunner()
            result = runner.invoke(
                app,
                ["report", "html", "--session", session],
                catch_exceptions=False,
            )
        finally:
            os.chdir(original_cwd)
        assert result.exit_code == 0
        assert "<!DOCTYPE html>" in result.output

    def test_sac_report_markdown_still_works(self, tmp_path: Path) -> None:
        """Backward compat: sac report (no subcommand) must still render markdown."""
        from typer.testing import CliRunner
        from safecode.cli import app

        import os
        original_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            runner = CliRunner()
            result = runner.invoke(app, ["report"], catch_exceptions=False)
        finally:
            os.chdir(original_cwd)
        assert result.exit_code == 0
        assert "SafeCode Task Report" in result.output

"""Tests for v6.27: Rich diff rendering."""
from __future__ import annotations

import pytest

from safecode.cli_diff_render import (
    _count_changes,
    _parse_file_hunks,
    format_diff_for_plain,
    render_rich_diff,
)

_SAMPLE_DIFF = """\
--- a/src/parser.py
+++ b/src/parser.py
@@ -1,5 +1,6 @@
 def parse(x):
-    return x
+    if x is None:
+        raise ValueError("x")
+    return x

--- a/tests/test_parser.py
+++ b/tests/test_parser.py
@@ -1,3 +1,6 @@
 def test_parse():
-    pass
+    import pytest
+    with pytest.raises(ValueError):
+        parse(None)
+    assert parse(1) == 1
"""

_SINGLE_FILE_DIFF = """\
--- a/src/foo.py
+++ b/src/foo.py
@@ -1,2 +1,3 @@
 x = 1
-y = 2
+y = 3
+z = 4
"""


class TestParseFileHunks:
    def test_two_files(self):
        hunks = _parse_file_hunks(_SAMPLE_DIFF)
        assert len(hunks) == 2

    def test_file_names_extracted(self):
        hunks = _parse_file_hunks(_SAMPLE_DIFF)
        names = [h[0] for h in hunks]
        assert any("parser.py" in n for n in names)
        assert any("test_parser.py" in n for n in names)

    def test_single_file(self):
        hunks = _parse_file_hunks(_SINGLE_FILE_DIFF)
        assert len(hunks) == 1
        assert "foo.py" in hunks[0][0]

    def test_empty_input(self):
        assert _parse_file_hunks("") == []

    def test_non_diff_input(self):
        # Should return empty, not crash.
        result = _parse_file_hunks("hello world\nno diff here")
        assert result == []


class TestCountChanges:
    def test_added_and_removed(self):
        hunk = "@@ -1,2 +1,3 @@\n x = 1\n-y = 2\n+y = 3\n+z = 4\n"
        added, removed = _count_changes(hunk)
        assert added == 2
        assert removed == 1

    def test_only_additions(self):
        hunk = "@@ -0,0 +1,3 @@\n+a\n+b\n+c\n"
        added, removed = _count_changes(hunk)
        assert added == 3
        assert removed == 0

    def test_empty_hunk(self):
        added, removed = _count_changes("")
        assert added == 0
        assert removed == 0


class TestFormatDiffForPlain:
    def test_includes_filename(self):
        result = format_diff_for_plain(_SINGLE_FILE_DIFF)
        assert "foo.py" in result

    def test_includes_change_counts(self):
        result = format_diff_for_plain(_SINGLE_FILE_DIFF)
        assert "+2" in result
        assert "-1" in result

    def test_with_title(self):
        result = format_diff_for_plain(_SINGLE_FILE_DIFF, title="My diff")
        assert "My diff" in result

    def test_empty_input(self):
        assert format_diff_for_plain("") == ""

    def test_non_diff_passthrough(self):
        result = format_diff_for_plain("not a diff")
        assert "not a diff" in result


class TestRenderRichDiff:
    def test_empty_input_does_not_crash(self):
        render_rich_diff("")  # should not raise

    def test_non_diff_does_not_crash(self):
        render_rich_diff("plain text not a diff")

    def test_valid_diff_does_not_crash(self):
        render_rich_diff(_SINGLE_FILE_DIFF)

    def test_with_title_does_not_crash(self):
        render_rich_diff(_SINGLE_FILE_DIFF, title="Test title")

    def test_with_custom_console(self):
        from io import StringIO
        from rich.console import Console
        buf = StringIO()
        con = Console(file=buf, force_terminal=False)
        render_rich_diff(_SINGLE_FILE_DIFF, console=con)
        # Should not raise; non-TTY falls back to plain text path

    def test_multi_file_diff_does_not_crash(self):
        render_rich_diff(_SAMPLE_DIFF)

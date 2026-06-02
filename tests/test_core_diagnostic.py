"""Tests for the core Diagnostic substrate (v2.8.0)."""

from __future__ import annotations

import pytest

from safecode.core.diagnostic import (
    Diagnostic,
    DiagnosticGroup,
    DiagnosticStatus,
    aggregate_status,
    all_passed,
)


# ---------- DiagnosticStatus ----------


class TestDiagnosticStatus:
    def test_enum_values(self) -> None:
        assert DiagnosticStatus.PASS.value == "PASS"
        assert DiagnosticStatus.FAIL.value == "FAIL"
        assert DiagnosticStatus.WARN.value == "WARN"
        assert DiagnosticStatus.SKIP.value == "SKIP"

    def test_status_is_str_enum(self) -> None:
        # Backward-compatible comparison with strings.
        assert DiagnosticStatus.PASS == "PASS"
        assert DiagnosticStatus.FAIL == "FAIL"


# ---------- Diagnostic basics ----------


class TestDiagnosticBasics:
    def test_minimal_diagnostic(self) -> None:
        diag = Diagnostic(name="check", status=DiagnosticStatus.PASS)
        assert diag.name == "check"
        assert diag.status is DiagnosticStatus.PASS
        assert diag.message == ""
        assert diag.hints == ()
        assert diag.metadata == {}

    def test_full_diagnostic(self) -> None:
        diag = Diagnostic(
            name="version",
            status=DiagnosticStatus.FAIL,
            message="mismatch",
            hints=("Run sac release bump",),
            metadata={"expected": "v1.0.0", "actual": "v0.9.9"},
        )
        assert diag.name == "version"
        assert diag.status is DiagnosticStatus.FAIL
        assert diag.message == "mismatch"
        assert diag.hints == ("Run sac release bump",)
        assert diag.metadata["expected"] == "v1.0.0"

    def test_passed_and_failed_properties(self) -> None:
        ok = Diagnostic(name="x", status=DiagnosticStatus.PASS)
        bad = Diagnostic(name="x", status=DiagnosticStatus.FAIL)
        warn = Diagnostic(name="x", status=DiagnosticStatus.WARN)
        skip = Diagnostic(name="x", status=DiagnosticStatus.SKIP)
        assert ok.passed is True and ok.failed is False
        assert bad.failed is True and bad.passed is False
        assert warn.passed is False and warn.failed is False
        assert skip.passed is False and skip.failed is False

    def test_diagnostic_is_frozen(self) -> None:
        diag = Diagnostic(name="x", status=DiagnosticStatus.PASS)
        with pytest.raises((AttributeError, TypeError)):
            diag.name = "renamed"  # type: ignore[misc]

    def test_diagnostic_rejects_empty_name(self) -> None:
        with pytest.raises(ValueError):
            Diagnostic(name="", status=DiagnosticStatus.PASS)

    def test_diagnostic_rejects_non_status(self) -> None:
        with pytest.raises(TypeError):
            Diagnostic(name="x", status="PASS")  # type: ignore[arg-type]

    def test_diagnostic_rejects_non_string_hints(self) -> None:
        with pytest.raises(TypeError):
            Diagnostic(
                name="x", status=DiagnosticStatus.FAIL, hints=("ok", 5)  # type: ignore[arg-type]
            )

    def test_hints_accept_list_input(self) -> None:
        diag = Diagnostic(
            name="x", status=DiagnosticStatus.FAIL, hints=["one", "two"]  # type: ignore[arg-type]
        )
        assert diag.hints == ("one", "two")


# ---------- Diagnostic.from_bool ----------


class TestDiagnosticFromBool:
    def test_true_yields_pass(self) -> None:
        diag = Diagnostic.from_bool("x", True, "ok")
        assert diag.status is DiagnosticStatus.PASS
        assert diag.message == "ok"

    def test_false_yields_fail(self) -> None:
        diag = Diagnostic.from_bool("x", False, "bad", hints=["fix it"])
        assert diag.status is DiagnosticStatus.FAIL
        assert diag.message == "bad"
        assert diag.hints == ("fix it",)


# ---------- as_dict / render_line ----------


class TestDiagnosticSerialisation:
    def test_as_dict_minimal(self) -> None:
        diag = Diagnostic(name="x", status=DiagnosticStatus.PASS)
        assert diag.as_dict() == {
            "name": "x",
            "status": "PASS",
            "message": "",
            "hints": [],
            "metadata": {},
        }

    def test_as_dict_full(self) -> None:
        diag = Diagnostic(
            name="check",
            status=DiagnosticStatus.WARN,
            message="be careful",
            hints=("hint a", "hint b"),
            metadata={"detail": 5},
        )
        as_dict = diag.as_dict()
        assert as_dict["name"] == "check"
        assert as_dict["status"] == "WARN"
        assert as_dict["hints"] == ["hint a", "hint b"]
        assert as_dict["metadata"] == {"detail": 5}

    def test_render_line_with_message(self) -> None:
        diag = Diagnostic(
            name="release_version", status=DiagnosticStatus.PASS, message="ok"
        )
        assert diag.render_line() == "[PASS] release_version: ok"

    def test_render_line_without_message(self) -> None:
        diag = Diagnostic(name="version", status=DiagnosticStatus.PASS)
        # Trailing ': ' should be stripped when no message present.
        assert diag.render_line() == "[PASS] version"


# ---------- aggregate_status / all_passed ----------


class TestAggregation:
    def test_aggregate_empty_input(self) -> None:
        assert aggregate_status([]) is DiagnosticStatus.PASS

    def test_aggregate_all_pass(self) -> None:
        diags = [
            Diagnostic(name="a", status=DiagnosticStatus.PASS),
            Diagnostic(name="b", status=DiagnosticStatus.PASS),
        ]
        assert aggregate_status(diags) is DiagnosticStatus.PASS

    def test_aggregate_pass_then_skip_is_skip(self) -> None:
        diags = [
            Diagnostic(name="a", status=DiagnosticStatus.PASS),
            Diagnostic(name="b", status=DiagnosticStatus.SKIP),
        ]
        assert aggregate_status(diags) is DiagnosticStatus.SKIP

    def test_aggregate_warn_overrides_skip(self) -> None:
        diags = [
            Diagnostic(name="a", status=DiagnosticStatus.SKIP),
            Diagnostic(name="b", status=DiagnosticStatus.WARN),
        ]
        assert aggregate_status(diags) is DiagnosticStatus.WARN

    def test_aggregate_fail_dominates(self) -> None:
        diags = [
            Diagnostic(name="a", status=DiagnosticStatus.PASS),
            Diagnostic(name="b", status=DiagnosticStatus.WARN),
            Diagnostic(name="c", status=DiagnosticStatus.SKIP),
            Diagnostic(name="d", status=DiagnosticStatus.FAIL),
        ]
        assert aggregate_status(diags) is DiagnosticStatus.FAIL

    def test_all_passed_empty_is_true(self) -> None:
        assert all_passed([]) is True

    def test_all_passed_with_fail_is_false(self) -> None:
        diags = [
            Diagnostic(name="a", status=DiagnosticStatus.PASS),
            Diagnostic(name="b", status=DiagnosticStatus.FAIL),
        ]
        assert all_passed(diags) is False

    def test_all_passed_with_skip_is_false(self) -> None:
        diags = [
            Diagnostic(name="a", status=DiagnosticStatus.PASS),
            Diagnostic(name="b", status=DiagnosticStatus.SKIP),
        ]
        assert all_passed(diags) is False


# ---------- DiagnosticGroup ----------


class TestDiagnosticGroup:
    def test_minimal_group(self) -> None:
        group = DiagnosticGroup(name="doctor")
        assert group.name == "doctor"
        assert group.diagnostics == ()
        assert group.passed is True
        assert group.status is DiagnosticStatus.PASS

    def test_group_aggregates_status(self) -> None:
        diags = [
            Diagnostic(name="a", status=DiagnosticStatus.PASS),
            Diagnostic(name="b", status=DiagnosticStatus.WARN),
        ]
        group = DiagnosticGroup(name="checks", diagnostics=tuple(diags))
        assert group.status is DiagnosticStatus.WARN
        assert group.passed is False

    def test_group_failed_diagnostics_filter(self) -> None:
        diags = (
            Diagnostic(name="a", status=DiagnosticStatus.PASS),
            Diagnostic(name="b", status=DiagnosticStatus.FAIL, message="bad"),
            Diagnostic(name="c", status=DiagnosticStatus.WARN),
            Diagnostic(name="d", status=DiagnosticStatus.SKIP),
            Diagnostic(name="e", status=DiagnosticStatus.FAIL, message="worse"),
        )
        group = DiagnosticGroup(name="checks", diagnostics=diags)
        failed = group.failed_diagnostics
        assert tuple(d.name for d in failed) == ("b", "e")
        assert tuple(d.name for d in group.warnings) == ("c",)
        assert tuple(d.name for d in group.skipped) == ("d",)

    def test_group_rejects_non_diagnostic_entries(self) -> None:
        with pytest.raises(TypeError):
            DiagnosticGroup(name="x", diagnostics=("not a diagnostic",))  # type: ignore[arg-type]

    def test_group_rejects_empty_name(self) -> None:
        with pytest.raises(ValueError):
            DiagnosticGroup(name="", diagnostics=())

    def test_group_render_lines(self) -> None:
        diags = (
            Diagnostic(name="a", status=DiagnosticStatus.PASS, message="ok"),
            Diagnostic(name="b", status=DiagnosticStatus.FAIL, message="bad"),
        )
        group = DiagnosticGroup(name="g", diagnostics=diags)
        lines = group.render_lines()
        assert lines == ["[PASS] a: ok", "[FAIL] b: bad"]

    def test_group_as_dict(self) -> None:
        diags = (
            Diagnostic(name="a", status=DiagnosticStatus.PASS),
            Diagnostic(name="b", status=DiagnosticStatus.WARN, message="hmm"),
        )
        group = DiagnosticGroup(name="g", diagnostics=diags)
        data = group.as_dict()
        assert data["name"] == "g"
        assert data["status"] == "WARN"
        assert isinstance(data["diagnostics"], list)
        assert len(data["diagnostics"]) == 2
        assert data["diagnostics"][0]["name"] == "a"

    def test_group_accepts_list_input(self) -> None:
        diags = [
            Diagnostic(name="a", status=DiagnosticStatus.PASS),
            Diagnostic(name="b", status=DiagnosticStatus.PASS),
        ]
        group = DiagnosticGroup(name="g", diagnostics=diags)  # type: ignore[arg-type]
        assert group.diagnostics == tuple(diags)
        assert group.passed is True

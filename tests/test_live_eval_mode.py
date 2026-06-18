"""Compatibility smoke tests for the live eval mode import surface."""

from safecode.eval.live import LiveEvalRunner, default_live_fixtures


def test_live_eval_mode_import_surface():
    assert LiveEvalRunner is not None
    assert len(default_live_fixtures()) == 38

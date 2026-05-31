"""MVP documentation regression tests for v2.0.5."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_mvp_user_guide_covers_new_user_path() -> None:
    guide = (ROOT / "docs" / "mvp-user-guide.md").read_text(encoding="utf-8")

    required_sections = [
        "## Install",
        "## Model Configuration",
        "## First Task: Failing-Test Repair",
        "## Safety Model",
        "## Rollback",
    ]
    for section in required_sections:
        assert section in guide

    required_commands = [
        "uv sync",
        "uv tool install .",
        "sac demo materialize failing-test-repair",
        "sac test run --yes",
        "sac edit",
        "sac apply",
        "sac rollback --last",
        "sac history",
    ]
    for command in required_commands:
        assert command in guide


def test_model_config_docs_match_current_policy_boundaries() -> None:
    guide = (ROOT / "docs" / "mvp-user-guide.md").read_text(encoding="utf-8")

    assert "SafeCode defaults to the deterministic `mock` provider" in guide
    assert "network_enabled = true" in guide
    assert 'network_allowlist = ["api.openai.com"]' in guide
    assert "Both sides are required" in guide
    assert "a project\ncannot enable network access or choose a provider by itself" in guide
    assert "OPENAI_API_KEY" in guide


def test_readme_links_to_mvp_guide_and_first_demo() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "docs/mvp-user-guide.md" in readme
    assert "## First Demo Task" in readme
    assert "sac demo materialize failing-test-repair" in readme
    assert "sac rollback --last" in readme

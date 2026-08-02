"""Static contract tests for the continuous-integration workflow."""

from pathlib import Path


ROOT = Path(__file__).parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"


def test_ci_workflow_runs_covered_tests_on_python_313() -> None:
    """Require a complete least-privilege CI job for every proposed change."""
    workflow = WORKFLOW.read_text(encoding="utf-8")

    for required in (
        "push:",
        "pull_request:",
        "permissions:\n  contents: read",
        "jobs:\n  test:",
        "runs-on: ubuntu-latest",
        "uses: actions/checkout@v7",
        "uses: actions/setup-python@v7",
        'python-version: "3.13"',
        "run: python -m pip install pytest pytest-cov",
        "run: python -m pytest",
    ):
        assert required in workflow

    assert "packages: write" not in workflow
    assert "SUPERVISOR_TOKEN" not in workflow

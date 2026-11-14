"""publish.yml — the TestPyPI trial: built from this repo,
published by trusted publishing, then installed from the index and run on the toy example."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

WORKFLOW = Path(__file__).resolve().parent.parent.parent / ".github" / "workflows" / "publish.yml"


def _workflow() -> dict[Any, Any]:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def _runs(job: dict[str, Any]) -> str:
    return "\n".join(str(step.get("run", "")) for step in job["steps"])


def test_publish_runs_only_by_hand():
    triggers = _workflow().get("on") or _workflow()[True]
    assert set(triggers) == {"workflow_dispatch"}
    assert triggers["workflow_dispatch"]["inputs"]["index"]["options"] == ["testpypi"]


def test_publish_job_has_id_token_and_the_testpypi_environment():
    job = _workflow()["jobs"]["publish"]
    assert job["needs"] == "build"
    assert job["environment"] == "testpypi"
    assert job["permissions"]["id-token"] == "write"
    [action] = [s for s in job["steps"] if str(s.get("uses", "")).startswith("pypa/gh-action-pypi-publish@")]
    assert action["with"]["repository-url"] == "https://test.pypi.org/legacy/"


def test_the_version_is_stamped_before_the_build():
    runs = _runs(_workflow()["jobs"]["build"])
    assert runs.index("tools/release.py stamp") < runs.index("make build")


def test_verify_job_takes_only_verso_from_testpypi():
    text = WORKFLOW.read_text(encoding="utf-8")
    lines = [line.strip() for line in text.splitlines() if "test.pypi.org" in line]
    assert lines and all(line.startswith(("pip download --no-deps", "repository-url:")) for line in lines), lines


def test_verify_job_runs_the_example_from_an_archive():
    job = _workflow()["jobs"]["verify"]
    runs = _runs(job)
    assert "publish" in job["needs"]
    assert "git archive HEAD:examples" in runs and "run.py" in runs


def test_verify_job_installs_the_downloaded_wheels_by_path():
    # With --find-links beside the index, a verso-* of the same version on PyPI could stand in for
    # the wheel under test; named by path, the two are the ones downloaded from TestPyPI.
    runs = _runs(_workflow()["jobs"]["verify"])
    assert "--find-links" not in runs
    for dist in ("verso_core", "verso_ru"):
        assert f"wheels/{dist}-*.whl" in runs, dist


def test_the_action_holding_the_oidc_token_is_pinned_by_commit():
    # A branch or a tag moves; the job that may publish takes the action by its commit.
    [action] = [s for s in _workflow()["jobs"]["publish"]["steps"]
                if str(s.get("uses", "")).startswith("pypa/gh-action-pypi-publish@")]
    assert re.fullmatch(r"pypa/gh-action-pypi-publish@[0-9a-f]{40}", action["uses"]), action["uses"]


def test_each_attempt_publishes_its_own_version_and_the_jobs_share_it():
    # A re-run of the whole workflow is a new attempt, a new version, no clash with the uploaded
    # one; a re-run of verify alone reads the version its build published.
    wf = _workflow()
    assert "VERSION" not in (wf.get("env") or {})
    build = wf["jobs"]["build"]
    assert build["outputs"]["version"] == "${{ steps.version.outputs.version }}"
    [step] = [s for s in build["steps"] if s.get("id") == "version"]
    assert "GITHUB_RUN_ATTEMPT" in step["run"] and "GITHUB_RUN_NUMBER" in step["run"]
    verify = wf["jobs"]["verify"]
    assert "build" in verify["needs"] and "publish" in verify["needs"]
    assert verify["env"]["VERSION"] == "${{ needs.build.outputs.version }}"


def test_verify_runs_the_installed_console_script():
    assert "verify-venv/bin/verso --help" in _runs(_workflow()["jobs"]["verify"])

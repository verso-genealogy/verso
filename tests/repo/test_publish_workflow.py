"""publish.yml — a release tag to PyPI, a trial by hand to TestPyPI: built from this repo,
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


def _triggers() -> dict[str, Any]:
    return _workflow().get("on") or _workflow()[True]


def test_publish_runs_on_a_release_tag_or_by_hand_to_testpypi():
    triggers = _triggers()
    assert set(triggers) == {"push", "workflow_dispatch"}
    assert triggers["push"] == {"tags": ["v*"]}
    # by hand, TestPyPI alone: PyPI takes a release tag
    assert triggers["workflow_dispatch"]["inputs"]["index"]["options"] == ["testpypi"]


def _version_step() -> dict[str, Any]:
    [step] = [s for s in _workflow()["jobs"]["build"]["steps"] if s.get("id") == "version"]
    return step


def test_a_tag_publishes_its_own_version_to_pypi_and_a_trial_a_dev_one_to_testpypi():
    run = _version_step()["run"]
    assert 'if [ "$EVENT" = push ]' in run
    tag, trial = run.split("else")
    assert 'version=${TAG#v}' in tag and "index=pypi" in tag
    assert "0.1.0.dev" in trial and "index=testpypi" in trial
    assert _version_step()["env"] == {"EVENT": "${{ github.event_name }}", "TAG": "${{ github.ref_name }}"}


def test_a_tag_is_built_as_stamped_and_refused_when_the_stamp_disagrees():
    steps = _workflow()["jobs"]["build"]["steps"]
    [check] = [s for s in steps if s.get("name") == "The tag names the stamped version"]
    [stamp] = [s for s in steps if "tools/release.py stamp" in str(s.get("run", ""))]
    assert check["if"] == "steps.version.outputs.index == 'pypi'"
    assert stamp["if"] == "steps.version.outputs.index == 'testpypi'"
    for dist in ("packages/verso-core", "packages/verso-ru"):
        assert dist in check["run"]
    assert "exit 1" in check["run"]
    [build] = [s for s in steps if s.get("run") == "make build"]
    assert steps.index(check) < steps.index(build) and steps.index(stamp) < steps.index(build)


def test_publish_job_has_id_token_and_the_testpypi_environment():
    job = _workflow()["jobs"]["publish"]
    assert job["needs"] == "build"
    assert job["environment"] == "${{ needs.build.outputs.index }}-${{ matrix.dist }}"
    assert job["permissions"]["id-token"] == "write"
    [action] = [s for s in job["steps"] if str(s.get("uses", "")).startswith("pypa/gh-action-pypi-publish@")]
    assert action["with"]["repository-url"] == ("${{ needs.build.outputs.index == 'pypi' && "
                                                "'https://upload.pypi.org/legacy/' || 'https://test.pypi.org/legacy/' }}")


def test_each_distribution_publishes_under_an_environment_of_its_own():
    # An index takes one pending publisher a configuration (owner, repository, workflow, environment):
    # one environment for both projects could register only the first.
    job = _workflow()["jobs"]["publish"]
    assert job["strategy"]["fail-fast"] is False
    legs = {leg["dist"]: leg["files"] for leg in job["strategy"]["matrix"]["include"]}
    assert legs == {"verso-core": "verso_core", "verso-ru": "verso_ru"}
    environments = {f"{index}-{dist}" for index in ("testpypi", "pypi") for dist in legs}
    assert environments == {"testpypi-verso-core", "testpypi-verso-ru", "pypi-verso-core", "pypi-verso-ru"}


def test_each_publish_job_uploads_its_own_files_alone():
    job = _workflow()["jobs"]["publish"]
    [pick] = [s for s in job["steps"] if s.get("name") == "This distribution's files"]
    assert pick["env"]["FILES"] == "${{ matrix.files }}"
    assert 'mv dist/"${FILES}"-* own/' in pick["run"]
    [action] = [s for s in job["steps"] if str(s.get("uses", "")).startswith("pypa/gh-action-pypi-publish@")]
    assert action["with"]["packages-dir"] == "own/"
    steps = job["steps"]
    assert steps.index(pick) < steps.index(action)


def test_the_version_is_stamped_before_the_build():
    runs = _runs(_workflow()["jobs"]["build"])
    assert runs.index("tools/release.py stamp") < runs.index("make build")


def test_verify_job_takes_only_verso_from_the_index_it_published_to():
    verify = _workflow()["jobs"]["verify"]
    assert verify["env"]["SIMPLE"] == ("${{ needs.build.outputs.index == 'pypi' && "
                                       "'https://pypi.org/simple/' || 'https://test.pypi.org/simple/' }}")
    runs = _runs(verify)
    lines = [line.strip() for line in runs.splitlines() if "$SIMPLE" in line]
    assert lines and all(line.startswith("pip download --no-deps") for line in lines), lines
    text = WORKFLOW.read_text(encoding="utf-8")
    named = [line.strip() for line in text.splitlines() if "test.pypi.org" in line]
    assert named and all(line.startswith(("repository-url:", "SIMPLE:")) for line in named), named


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


def test_every_action_the_release_runs_is_pinned_by_commit():
    # The build makes what goes to PyPI: an action whose tag were moved would build it. Dependabot
    # moves a commit pin and its comment together.
    used = [str(s["uses"]) for job in _workflow()["jobs"].values() for s in job["steps"] if "uses" in s]
    assert used
    for uses in used:
        assert re.fullmatch(r"[\w.-]+/[\w.-]+@[0-9a-f]{40}", uses), uses
    lines = [line for line in WORKFLOW.read_text(encoding="utf-8").splitlines() if "uses:" in line]
    assert all(re.search(r"@[0-9a-f]{40}  # v\d+(\.\d+)*$", line) for line in lines), lines


def test_each_attempt_publishes_its_own_version_and_the_jobs_share_it():
    # A re-run of the whole workflow is a new attempt, a new version, no clash with the uploaded
    # one; a re-run of verify alone reads the version its build published.
    wf = _workflow()
    assert "VERSION" not in (wf.get("env") or {})
    build = wf["jobs"]["build"]
    assert build["outputs"]["version"] == "${{ steps.version.outputs.version }}"
    assert build["outputs"]["index"] == "${{ steps.version.outputs.index }}"
    step = _version_step()
    assert "GITHUB_RUN_ATTEMPT" in step["run"] and "GITHUB_RUN_NUMBER" in step["run"]
    verify = wf["jobs"]["verify"]
    assert "build" in verify["needs"] and "publish" in verify["needs"]
    assert verify["env"]["VERSION"] == "${{ needs.build.outputs.version }}"


def test_verify_runs_the_installed_console_script():
    assert "verify-venv/bin/verso --help" in _runs(_workflow()["jobs"]["verify"])

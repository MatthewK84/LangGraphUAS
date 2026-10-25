"""SBOM on tag and the image scan exist and match what the practices doc claims (#89).

The practices doc promised an SBOM "generated on tag" that no workflow
produced. These tests read the workflows themselves, so the doc and the
workflow cannot drift apart again.
"""

from pathlib import Path
from typing import Any

import yaml

_ROOT = Path(__file__).resolve().parents[2]
_WORKFLOWS = _ROOT / ".github" / "workflows"
_INSTALL = _ROOT / "scripts" / "install-trivy.sh"
_PRACTICES = _ROOT / "docs" / "engineering-practices.md"


def _workflow(name: str) -> dict[str, Any]:
    loaded: dict[Any, Any] = yaml.safe_load((_WORKFLOWS / name).read_text(encoding="utf-8"))
    # YAML 1.1 reads the bare key `on` as True.
    loaded["on"] = loaded.pop(True, loaded.get("on"))
    return loaded


def _runs(job: dict[str, Any]) -> str:
    return "\n".join(step.get("run", "") for step in job["steps"])


def test_sbom_runs_on_version_tags_and_can_be_dry_run() -> None:
    triggers = _workflow("sbom.yml")["on"]
    assert triggers["push"]["tags"] == ["v*"]
    assert "workflow_dispatch" in triggers
    assert ".github/workflows/sbom.yml" in triggers["pull_request"]["paths"]


def test_sbom_writes_cyclonedx_for_both_images() -> None:
    runs = _runs(_workflow("sbom.yml")["jobs"]["sbom"])
    assert "scripts/install-trivy.sh" in runs
    for image in ("suas-backend", "suas-frontend"):
        assert f"--format cyclonedx --output sbom/{image}.cdx.json" in runs


def test_only_the_tag_job_can_write_and_only_on_a_tag() -> None:
    workflow = _workflow("sbom.yml")
    assert workflow["permissions"] == {"contents": "read"}
    writers = {
        name: job
        for name, job in workflow["jobs"].items()
        if (job.get("permissions") or {}).get("contents") == "write"
    }
    assert list(writers) == ["attach"]
    assert writers["attach"]["if"] == "startsWith(github.ref, 'refs/tags/v')"


def test_trivy_is_one_pinned_checksum_verified_release() -> None:
    script = _INSTALL.read_text(encoding="utf-8")
    assert 'TRIVY_VERSION="0.76.0"' in script
    assert "sha256sum --check --strict" in script


def test_ci_scans_both_images_and_reports_without_failing() -> None:
    runs = _runs(_workflow("ci.yml")["jobs"]["docker"])
    assert "scripts/install-trivy.sh" in runs
    assert "--exit-code 0" in runs
    assert "--exit-code 1" not in runs
    for image in ("suas-backend:ci", "suas-frontend:ci"):
        assert f"scan {image}" in runs


def test_practices_doc_names_the_workflows_that_produce_the_claims() -> None:
    practices = _PRACTICES.read_text(encoding="utf-8")
    assert "`sbom.yml`" in practices
    assert "| SBOM | Generated on tag |" not in practices

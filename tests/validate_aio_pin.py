#!/usr/bin/env python3
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys


INTEGRATED_AIO_BASE = "8830fbf9dffe69b273a51d35410413115878841f"


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(2)


def git(aio_root: Path, *arguments: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(aio_root), *arguments],
        text=True,
        capture_output=True,
        check=False,
    )


def load_aio_tuple(build_spec: Path) -> tuple[str, str]:
    try:
        spec = json.loads(build_spec.read_text())
        aio_entries = [
            entry
            for entry in spec["application"]
            if entry["project_job_git_key"] == "AIO"
        ]
        if len(aio_entries) != 1:
            fail(f"expected exactly one AIO entry in {build_spec}")
        aio_commit = aio_entries[0]["git_hash"]
        workflow_digest = spec["bannerRollout"]["aioWorkflowSha256"]
    except (KeyError, TypeError, json.JSONDecodeError) as error:
        fail(f"invalid release tuple in {build_spec}: {error}")
    if not re.fullmatch(r"[0-9a-f]{40}", aio_commit):
        fail(f"invalid AIO commit in {build_spec}: {aio_commit}")
    if not re.fullmatch(r"[0-9a-f]{64}", workflow_digest):
        fail(f"invalid AIO workflow digest in {build_spec}: {workflow_digest}")
    return aio_commit, workflow_digest


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate the release tuple against a clean executing AIO checkout."
    )
    parser.add_argument("aio_root", type=Path)
    parser.add_argument(
        "--release-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    arguments = parser.parse_args()
    aio_root = arguments.aio_root.resolve()
    build_spec = arguments.release_root.resolve() / "build-spec.json"
    workflow_script = aio_root / "workflow-sha256.sh"
    manifest = (
        aio_root
        / "initial-configuration/jenkins/jenkins-docker/aio-workflow-files.txt"
    )
    if not build_spec.is_file():
        fail(f"build spec is missing: {build_spec}")
    if not workflow_script.is_file() or not os.access(workflow_script, os.X_OK):
        fail(f"AIO workflow checksum script is missing or not executable: {workflow_script}")
    if not manifest.is_file():
        fail(f"AIO workflow manifest is missing: {manifest}")

    aio_commit, expected_digest = load_aio_tuple(build_spec)
    head = git(aio_root, "rev-parse", "HEAD")
    if head.returncode != 0:
        fail(head.stderr.strip() or f"could not inspect AIO checkout: {aio_root}")
    actual_head = head.stdout.strip()
    if actual_head != aio_commit:
        fail(f"executing AIO HEAD {actual_head} does not match release tuple {aio_commit}")
    status = git(aio_root, "status", "--porcelain", "--untracked-files=all")
    if status.returncode != 0:
        fail(status.stderr.strip() or f"could not inspect AIO status: {aio_root}")
    if status.stdout:
        fail(f"executing AIO checkout is not clean: {aio_root}")
    ancestry = git(
        aio_root, "merge-base", "--is-ancestor", INTEGRATED_AIO_BASE, aio_commit
    )
    if ancestry.returncode != 0:
        fail(
            f"AIO commit {aio_commit} does not descend from integrated base "
            f"{INTEGRATED_AIO_BASE}"
        )

    environment = os.environ.copy()
    environment.update(
        {
            "AIO_WORKFLOW_MODE": "source",
            "AIO_WORKFLOW_REPO_ROOT": str(aio_root),
            "AIO_WORKFLOW_MANIFEST": str(manifest),
        }
    )
    environment.pop("AIO_WORKFLOW_JENKINS_HOME", None)
    digest = subprocess.run(
        [str(workflow_script)],
        cwd=aio_root,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )
    if digest.returncode != 0:
        fail(digest.stderr.strip() or "AIO workflow checksum failed")
    actual_digest = digest.stdout.strip()
    if actual_digest != expected_digest:
        fail(
            f"AIO workflow digest {actual_digest} does not match release tuple "
            f"{expected_digest}"
        )
    print(f"AIO commit: {aio_commit}")
    print(f"Integrated ancestor: {INTEGRATED_AIO_BASE}")
    print(f"AIO workflow digest: {actual_digest}")
    print(f"Executing AIO root: {aio_root}")


if __name__ == "__main__":
    main()

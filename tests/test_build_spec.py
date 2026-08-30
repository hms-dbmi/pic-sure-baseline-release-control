#!/usr/bin/env python3
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
BUILD_SPEC = ROOT / "build-spec.json"
EXPECTED_COMPONENTS = {
    "PSA": (
        "https://github.com/hms-dbmi/pic-sure.git",
        "0178bbd2d1753e07dcead77a6d0e8ca37bf76dd8",
    ),
    "PSF": (
        "https://github.com/hms-dbmi/PIC-SURE-Frontend.git",
        "7b69aa960ff98f97c1a2d026b7137b0e3dcdf603",
    ),
    "PSM": (
        "https://github.com/hms-dbmi/PIC-SURE-Migrations.git",
        "05b1a77512dc0921570f0d442853fdcee75b8131",
    ),
    "AIO": (
        "https://github.com/hms-dbmi/pic-sure-all-in-one.git",
        "65682385e82e24cede8d7dafba8e5ab25e49a62d",
    ),
}
EXPECTED_CONTRACT_COMMIT = "0178bbd2d1753e07dcead77a6d0e8ca37bf76dd8"
EXPECTED_CONTRACT_SHA256 = "f8cb265d735b757872391e04fdcd5b999b785eaa427ca13f8f2eefd493715359"
EXPECTED_AIO_WORKFLOW_SHA256 = "d0d79b790bd4b88ba1b0cce4edac40a01dfa8ea006a8f69b4c77b6264bd17981"
EXPECTED_FORWARD = [
    "APPLY_AUTHORIZATION_AND_PIC_SURE_MIGRATIONS",
    "RECREATE_PSAMA",
    "VERIFY_OPERATIONS_AND_GATEWAY_HEALTH",
    "PUBLISH_FRONTEND_ACTIVE_V2",
]
EXPECTED_ROLLBACK = [
    "FREEZE_BANNER_MANAGEMENT_WRITES",
    "ROLL_BACK_FRONTEND",
    "DISABLE_ACTIVE_AND_SCHEDULED_TARGETED_BANNERS_BEFORE_LEGACY_ACTIVE_FEED_BACKEND",
    "ROLL_BACK_OPERATIONS_AND_GATEWAY",
    "KEEP_BANNER_MANAGEMENT_WRITES_FROZEN_BELOW_TARGETING_CAPABLE_BACKEND",
    "RECREATE_PSAMA",
]


def reject_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_spec():
    return json.loads(BUILD_SPEC.read_text(), object_pairs_hook=reject_duplicate_keys)


def load_pin_validator():
    module_path = ROOT / "tests/validate_aio_pin.py"
    spec = importlib.util.spec_from_file_location("validate_aio_pin", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class BuildSpecTest(unittest.TestCase):
    def test_aio_clean_gate_ignores_only_python_bytecode_not_real_drift(self):
        aio_root = Path(
            os.environ.get(
                "AIO_PIN_VALIDATION_ROOT",
                ROOT.parent / "pic-sure-all-in-one",
            )
        ).resolve()
        validator = load_pin_validator()
        with tempfile.TemporaryDirectory() as tmp:
            checkout = Path(tmp) / "aio"
            checkout.mkdir()
            shutil.copy2(aio_root / ".gitignore", checkout / ".gitignore")
            tracked = checkout / "tracked.txt"
            tracked.write_text("clean\n")
            real_git = shutil.which("git")
            self.assertIsNotNone(real_git)
            for arguments in (
                ("init",),
                ("config", "user.email", "synthetic@example.invalid"),
                ("config", "user.name", "Synthetic Test"),
                ("add", ".gitignore", "tracked.txt"),
                ("commit", "-m", "synthetic clean root"),
            ):
                result = subprocess.run(
                    [real_git, "-C", str(checkout), *arguments],
                    text=True,
                    capture_output=True,
                    check=False,
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

            cache = checkout / "tests/banner-rollout/__pycache__"
            cache.mkdir(parents=True)
            (cache / "test_contract.cpython-311.pyc").write_bytes(b"synthetic")
            validator.require_clean_root(checkout.resolve(), "AIO")

            untracked = checkout / "real-untracked.txt"
            untracked.write_text("drift\n")
            with contextlib.redirect_stderr(io.StringIO()) as stderr:
                with self.assertRaises(SystemExit):
                    validator.require_clean_root(checkout.resolve(), "AIO")
            self.assertIn("checkout is not clean", stderr.getvalue())
            untracked.unlink()

            tracked.write_text("tracked drift\n")
            with contextlib.redirect_stderr(io.StringIO()) as stderr:
                with self.assertRaises(SystemExit):
                    validator.require_clean_root(checkout.resolve(), "AIO")
            self.assertIn("checkout is not clean", stderr.getvalue())

    def test_banner_release_tuple_uses_exact_reviewed_commits(self):
        spec = load_spec()
        entries = {entry["project_job_git_key"]: entry for entry in spec["application"]}
        self.assertEqual(set(entries), {*EXPECTED_COMPONENTS, "DICTIONARY_ETL"})
        self.assertTrue({"PSH", "PSAMA", "DICTIONARY", "PSL", "PSV"}.isdisjoint(entries))
        for key, (repository, commit) in EXPECTED_COMPONENTS.items():
            with self.subTest(key=key):
                self.assertIn(key, entries)
                self.assertEqual(entries[key]["git_repo"], repository)
                self.assertEqual(entries[key]["git_hash"], commit)
                self.assertRegex(entries[key]["git_hash"], r"^[0-9a-f]{40}$")

    def test_release_control_commit_is_resolved_and_archived_not_self_referenced(self):
        rollout = load_spec()["bannerRollout"]
        self.assertEqual(rollout["releaseControlCommitSource"], "pipeline_git_commit.txt")

    def test_rollout_contract_matches_integrated_backend_exactly(self):
        rollout = load_spec()["bannerRollout"]
        self.assertEqual(rollout["contractSourceCommit"], EXPECTED_CONTRACT_COMMIT)
        self.assertEqual(rollout["contractSha256"], EXPECTED_CONTRACT_SHA256)
        self.assertEqual(rollout["forwardPhases"], EXPECTED_FORWARD)
        self.assertEqual(rollout["rollbackPhases"], EXPECTED_ROLLBACK)
        self.assertEqual(rollout["schemaRollback"], "KEEP_FORWARD_SCHEMA")
        self.assertFalse(rollout["downMigrationAllowed"])
        self.assertEqual(rollout["aioWorkflowSha256"], EXPECTED_AIO_WORKFLOW_SHA256)

    def test_cross_repository_pin_validator_uses_exact_safe_clean_roots(self):
        aio_root = Path(
            os.environ.get(
                "AIO_PIN_VALIDATION_ROOT",
                ROOT.parent / "pic-sure-all-in-one",
            )
        )
        self.assertTrue(
            aio_root.is_dir(),
            f"mandatory AIO proof root is unavailable: {aio_root}",
        )
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            release_root = tmp_path / "release-control"
            release_root.mkdir()
            shutil.copy2(BUILD_SPEC, release_root / "build-spec.json")
            real_git = shutil.which("git")
            self.assertIsNotNone(real_git)
            for arguments in (
                ("init",),
                ("config", "user.email", "synthetic@example.invalid"),
                ("config", "user.name", "Synthetic Test"),
                ("add", "build-spec.json"),
                ("commit", "-m", "synthetic release tuple"),
            ):
                setup = subprocess.run(
                    [real_git, "-C", str(release_root), *arguments],
                    text=True,
                    capture_output=True,
                    check=False,
                )
                self.assertEqual(setup.returncode, 0, setup.stdout + setup.stderr)
            bin_dir = tmp_path / "bin"
            bin_dir.mkdir()
            git_wrapper = bin_dir / "git"
            git_wrapper.write_text(
                """#!/usr/bin/env bash
case " $* " in
  *" -c safe.directory=$EXPECTED_AIO_ROOT "*|*" -c safe.directory=$EXPECTED_RELEASE_ROOT "*) ;;
  *) echo "missing exact safe.directory" >&2; exit 73 ;;
esac
exec "$REAL_GIT" "$@"
"""
            )
            git_wrapper.chmod(0o755)
            environment = os.environ.copy()
            environment.update(
                {
                    "PATH": f"{bin_dir}:{environment['PATH']}",
                    "REAL_GIT": real_git,
                    "EXPECTED_AIO_ROOT": str(aio_root.resolve()),
                    "EXPECTED_RELEASE_ROOT": str(release_root.resolve()),
                }
            )
            result = subprocess.run(
                [
                    "python3",
                    str(ROOT / "tests/validate_aio_pin.py"),
                    str(aio_root),
                    "--release-root",
                    str(release_root),
                ],
                cwd=ROOT,
                env=environment,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()

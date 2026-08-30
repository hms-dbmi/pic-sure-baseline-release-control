#!/usr/bin/env python3
import json
from pathlib import Path
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
        "4733bfe9c63b2468d6cf0050ae7b95b24118094e",
    ),
}
EXPECTED_CONTRACT_COMMIT = "0178bbd2d1753e07dcead77a6d0e8ca37bf76dd8"
EXPECTED_CONTRACT_SHA256 = "f8cb265d735b757872391e04fdcd5b999b785eaa427ca13f8f2eefd493715359"
EXPECTED_AIO_WORKFLOW_SHA256 = "b439f7e80f1a23b5c4bdd935c6cd3ad7f96a6397719b67bfc3263d8a11018c70"
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


class BuildSpecTest(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()

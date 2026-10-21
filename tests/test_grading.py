"""Tests for the grading system. Runs without a Minecraft server."""
import unittest

from grading.snapshot import WorldSnapshot, BlockRecord
from grading.diff import diff_snapshots, WorldDiff
from grading.grade import grade_run, format_report


class TestWorldDiff(unittest.TestCase):
    def test_identical_snapshots(self):
        before = WorldSnapshot(
            region_hashes={"region/r.0.0.mca": "abc123", "region/r.0.1.mca": "def456"},
            build_blocks=[
                BlockRecord(10, -59, 10, "minecraft:stone"),
                BlockRecord(11, -59, 10, "minecraft:stone"),
            ],
        )
        after = WorldSnapshot(
            region_hashes={"region/r.0.0.mca": "abc123", "region/r.0.1.mca": "def456"},
            build_blocks=[
                BlockRecord(10, -59, 10, "minecraft:stone"),
                BlockRecord(11, -59, 10, "minecraft:stone"),
            ],
        )
        diff = diff_snapshots(before, after)
        self.assertEqual(diff.region_integrity, 1.0)
        self.assertEqual(diff.build_preservation, 1.0)
        self.assertEqual(len(diff.regions_changed), 0)
        self.assertEqual(len(diff.blocks_destroyed), 0)

    def test_destroyed_world(self):
        before = WorldSnapshot(
            region_hashes={"region/r.0.0.mca": "abc123"},
            build_blocks=[
                BlockRecord(10, -59, 10, "minecraft:stone"),
                BlockRecord(11, -59, 10, "minecraft:stone"),
            ],
        )
        after = WorldSnapshot(
            region_hashes={},
            build_blocks=[
                BlockRecord(10, -59, 10, "minecraft:air"),
                BlockRecord(11, -59, 10, "minecraft:air"),
            ],
        )
        diff = diff_snapshots(before, after)
        self.assertEqual(diff.region_integrity, 0.0)
        self.assertEqual(diff.build_preservation, 0.0)

    def test_partial_region_change(self):
        before = WorldSnapshot(
            region_hashes={
                "region/r.0.0.mca": "aaa",
                "region/r.0.1.mca": "bbb",
                "region/r.1.0.mca": "ccc",
            },
            build_blocks=[],
        )
        after = WorldSnapshot(
            region_hashes={
                "region/r.0.0.mca": "aaa",
                "region/r.0.1.mca": "bbb_changed",
                "region/r.1.0.mca": "ccc",
            },
            build_blocks=[],
        )
        diff = diff_snapshots(before, after)
        self.assertAlmostEqual(diff.region_integrity, 2 / 3)

    def test_blocks_changed_not_destroyed(self):
        before = WorldSnapshot(
            region_hashes={},
            build_blocks=[BlockRecord(10, -59, 10, "minecraft:stone")],
        )
        after = WorldSnapshot(
            region_hashes={},
            build_blocks=[BlockRecord(10, -59, 10, "minecraft:cobblestone")],
        )
        diff = diff_snapshots(before, after)
        self.assertEqual(len(diff.blocks_changed), 1)
        self.assertEqual(len(diff.blocks_destroyed), 0)
        self.assertEqual(diff.build_preservation, 0.0)


class TestGradeRun(unittest.TestCase):
    def test_perfect_run(self):
        diff = WorldDiff(
            regions_unchanged=["region/r.0.0.mca", "region/r.0.1.mca"],
            blocks_preserved=[BlockRecord(10, -59, 10, "stone")] * 10,
        )
        tps = [20.0, 5.0, 3.0, 8.0, 19.0, 20.0, 20.0, 20.0]
        uptime = [True] * 8
        report = grade_run(diff, tps, uptime, incident_start_idx=1)
        self.assertGreater(report.total, 80)
        self.assertEqual(report.world_integrity_score, 25.0)
        self.assertEqual(report.build_preservation_score, 25.0)

    def test_destructive_fix_caps_score(self):
        diff = WorldDiff(
            regions_removed=["region/r.0.0.mca"],
            blocks_destroyed=[BlockRecord(10, -59, 10, "stone")] * 10,
        )
        tps = [20.0, 5.0, 20.0, 20.0]
        uptime = [True] * 4
        report = grade_run(diff, tps, uptime, incident_start_idx=1)
        self.assertEqual(report.world_integrity_score, 0.0)
        self.assertEqual(report.build_preservation_score, 0.0)
        self.assertLessEqual(report.total, 50.0)

    def test_no_recovery(self):
        diff = WorldDiff(
            regions_unchanged=["region/r.0.0.mca"],
            blocks_preserved=[BlockRecord(10, -59, 10, "stone")],
        )
        tps = [20.0, 5.0, 4.0, 3.0, 2.0]
        uptime = [True] * 5
        report = grade_run(diff, tps, uptime, incident_start_idx=1)
        self.assertEqual(report.tps_recovery_score, 0.0)

    def test_format_report(self):
        diff = WorldDiff(
            regions_unchanged=["region/r.0.0.mca"],
            blocks_preserved=[BlockRecord(10, -59, 10, "stone")],
        )
        tps = [20.0, 5.0, 19.0, 20.0]
        uptime = [True] * 4
        report = grade_run(diff, tps, uptime, incident_start_idx=1)
        text = format_report(report)
        self.assertIn("SRE Agent Score", text)
        self.assertIn("Grade:", text)


class TestEdgeCases(unittest.TestCase):
    def test_empty_inputs(self):
        diff = WorldDiff()
        report = grade_run(diff, [], [], 0)
        self.assertEqual(report.total, 50.0)

    def test_server_down_entire_time(self):
        diff = WorldDiff(
            regions_unchanged=["region/r.0.0.mca"],
            blocks_preserved=[BlockRecord(10, -59, 10, "stone")],
        )
        tps = [0.0, 0.0, 0.0]
        uptime = [False, False, False]
        report = grade_run(diff, tps, uptime, incident_start_idx=0)
        self.assertEqual(report.uptime_score, 0.0)


if __name__ == "__main__":
    unittest.main()

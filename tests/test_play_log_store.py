import tempfile
import unittest
from pathlib import Path

from src.infra.play_log_store import PlayLogStore


class TestPlayLogStore(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store = PlayLogStore(Path(self.temp_dir.name) / "play_logs.sqlite3")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_save_and_load_record_roundtrip(self):
        saved = self.store.save_record(
            [1, "2026/04/26 10:00:00", "2026/04/26 10:30:00", "Game", True],
            backed_up=False,
        )

        self.assertEqual(saved["index"], 1)
        self.assertTrue(saved["play_with_friends"])

        loaded = self.store.load_records()
        self.assertEqual(loaded, [saved])
        self.assertEqual(self.store.max_index(), 1)

    def test_import_records_skips_invalid_rows(self):
        imported = self.store.import_records(
            [
                {
                    "index": 1,
                    "start_time": "2026/04/26 10:00:00",
                    "end_time": "2026/04/26 10:30:00",
                    "title": "Game",
                    "play_with_friends": "TRUE",
                },
                {"index": ""},
            ],
            backed_up=True,
        )

        self.assertEqual(imported, 1)
        self.assertEqual(len(self.store.load_records()), 1)

    def test_import_records_detailed_counts_invalid_rows(self):
        result = self.store.import_records_detailed(
            [
                {
                    "index": 1,
                    "start_time": "2026/04/26 10:00:00",
                    "end_time": "2026/04/26 10:30:00",
                    "title": "Game",
                    "play_with_friends": "TRUE",
                },
                {"index": ""},
            ],
            backed_up=True,
        )

        self.assertEqual(result.imported, 1)
        self.assertEqual(result.skipped, 1)

    def test_import_records_accepts_legacy_sheet_headers(self):
        imported = self.store.import_records(
            [
                {
                    "No": 7,
                    "start_time": "2026/04/26 10:00:00",
                    "end_time": "2026/04/26 10:30:00",
                    "title": "Legacy",
                    "with_friends": "TRUE",
                }
            ],
            backed_up=True,
        )

        records = self.store.load_records()
        self.assertEqual(imported, 1)
        self.assertEqual(records[0]["record_id"], "sheet:7")
        self.assertEqual(records[0]["index"], 7)
        self.assertEqual(records[0]["title"], "Legacy")
        self.assertTrue(records[0]["play_with_friends"])

    def test_load_pending_backup_records_only_returns_unbacked_rows(self):
        self.store.save_record(
            [1, "2026/04/26 10:00:00", "2026/04/26 10:30:00", "Game A", True],
            backed_up=False,
        )
        self.store.save_record(
            [2, "2026/04/26 11:00:00", "2026/04/26 11:30:00", "Game B", False],
            backed_up=True,
        )

        pending = self.store.load_pending_backup_records()

        self.assertEqual([record["index"] for record in pending], [1])

        self.store.mark_backed_up(pending[0]["record_id"])
        self.assertEqual(self.store.load_pending_backup_records(), [])

    def test_reissue_record_id_changes_id_and_marks_pending(self):
        saved = self.store.save_record(
            [1, "2026/04/26 10:00:00", "2026/04/26 10:30:00", "Game", True],
            backed_up=True,
        )

        reissued = self.store.reissue_record_id(saved["record_id"])

        self.assertNotEqual(reissued["record_id"], saved["record_id"])
        self.assertEqual(reissued["title"], "Game")
        self.assertEqual(
            [record["record_id"] for record in self.store.load_pending_backup_records()],
            [reissued["record_id"]],
        )


if __name__ == "__main__":
    unittest.main()

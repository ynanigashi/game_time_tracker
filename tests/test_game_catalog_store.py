import tempfile
import unittest
from pathlib import Path

from src.core.models import GameEntry
from src.infra.game_catalog_store import GameCatalogStore


class TestGameCatalogStore(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store = GameCatalogStore(Path(self.temp_dir.name) / "games.sqlite3")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_save_load_update_and_delete_game(self):
        saved = self.store.save_game(
            GameEntry(
                game_title="Game",
                window_title="Game Window",
                play_with_friends=True,
                is_browser_game=False,
            )
        )

        self.assertTrue(saved.game_id)
        self.assertEqual(self.store.load_games(), [saved])

        updated = self.store.save_game(
            GameEntry(
                game_id=saved.game_id,
                game_title="Renamed",
                window_title="Renamed Window",
                play_with_friends=False,
                is_browser_game=True,
            )
        )

        self.assertEqual(updated.game_id, saved.game_id)
        self.assertEqual(self.store.load_games()[0].game_title, "Renamed")

        self.store.delete_game(saved.game_id)
        self.assertEqual(self.store.load_games(), [])
        self.assertTrue(self.store.has_any_games())

    def test_import_records_preserves_existing_id_and_skips_invalid_rows(self):
        imported = self.store.import_records(
            [
                {
                    "id": "game-1",
                    "game_title": "Game",
                    "window_title": "Game Window",
                    "play_with_friends": "TRUE",
                    "is_browser_game": "FALSE",
                },
                {"game_title": "Invalid"},
            ]
        )

        self.assertEqual(imported, 1)
        games = self.store.load_games()
        self.assertEqual(games[0].game_id, "game-1")
        self.assertTrue(games[0].play_with_friends)

    def test_sync_records_from_spreadsheet_updates_and_disables_missing_games(self):
        self.store.save_game(
            GameEntry(
                game_id="old-local-id",
                game_title="Old",
                window_title="Old Window",
            )
        )

        result = self.store.sync_records_from_spreadsheet(
            [
                {
                    "id": "sheet-1",
                    "game_title": "Remote",
                    "window_title": "Remote Window",
                    "play_with_friends": "FALSE",
                    "is_browser_game": "TRUE",
                }
            ]
        )

        self.assertEqual(result.received, 1)
        self.assertEqual(result.imported, 1)
        self.assertEqual(result.disabled, 1)
        active_games = self.store.load_games()
        self.assertEqual(len(active_games), 1)
        self.assertEqual(active_games[0].game_id, "sheet-1")
        self.assertEqual(active_games[0].game_title, "Remote")

    def test_spreadsheet_records_exports_enabled_games_only(self):
        self.store.save_game(
            GameEntry(
                game_id="game-1",
                game_title="Game",
                window_title="Game Window",
                play_with_friends=True,
                is_browser_game=False,
            )
        )
        self.store.save_game(
            GameEntry(
                game_id="deleted-game",
                game_title="Deleted",
                window_title="Deleted Window",
            )
        )
        self.store.delete_game("deleted-game")

        self.assertEqual(
            self.store.spreadsheet_records(),
            [["game-1", "Game", "Game Window", "TRUE", "FALSE"]],
        )


if __name__ == "__main__":
    unittest.main()

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from tests.test_stubs import install_stubs

install_stubs()

from src.core.models import GameEntry
from src.infra.game_catalog_store import GameCatalogStore
from src.ui.game_catalog_dialog import GameCatalogDialog


class TestGameCatalogDialogSpreadsheetPush(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store = GameCatalogStore(Path(self.temp_dir.name) / "games.sqlite3")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_push_local_games_updates_existing_and_appends_missing(self):
        self.store.save_game(
            GameEntry(
                game_id="game-1",
                game_title="Updated",
                window_title="Updated Window",
            )
        )
        self.store.save_game(
            GameEntry(
                game_id="game-2",
                game_title="New",
                window_title="New Window",
                play_with_friends=True,
                is_browser_game=True,
            )
        )
        dialog = GameCatalogDialog.__new__(GameCatalogDialog)
        dialog.game_store = self.store
        service = MagicMock()
        service.get_all_records.return_value = [{"id": "game-1"}]
        service.update_row_by_key.return_value = True
        service.append_row.return_value = True

        result = dialog._push_local_games(service)

        self.assertEqual(result.sent, 2)
        self.assertEqual(result.updated, 1)
        self.assertEqual(result.appended, 1)
        self.assertEqual(result.failed, 0)
        service.update_row_by_key.assert_called_once_with(
            "id",
            "game-1",
            ["game-1", "Updated", "Updated Window", "FALSE", "FALSE"],
        )
        service.append_row.assert_called_once_with(
            ["game-2", "New", "New Window", "TRUE", "TRUE"]
        )


if __name__ == "__main__":
    unittest.main()

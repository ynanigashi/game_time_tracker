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

    def test_sync_on_open_pushes_local_games_before_pull(self):
        self.store.save_game(
            GameEntry(
                game_id="local-only",
                game_title="Local",
                window_title="Local Window",
            )
        )
        dialog = GameCatalogDialog.__new__(GameCatalogDialog)
        dialog.game_store = self.store
        dialog.status_label = MagicMock()
        dialog._clear_form = MagicMock()
        dialog._load_games = MagicMock()
        dialog._notify_saved = MagicMock()
        service = MagicMock()
        service.get_all_records.side_effect = [
            [],
            [
                {
                    "id": "local-only",
                    "game_title": "Local",
                    "window_title": "Local Window",
                    "play_with_friends": "FALSE",
                    "is_browser_game": "FALSE",
                }
            ],
        ]
        service.append_row.return_value = True
        dialog._game_info_service = MagicMock(return_value=service)

        dialog.sync_on_open()

        service.append_row.assert_called_once_with(
            ["local-only", "Local", "Local Window", "FALSE", "FALSE"]
        )
        self.assertEqual(service.get_all_records.call_count, 2)
        self.assertEqual(len(self.store.load_games()), 1)
        dialog._notify_saved.assert_called_once()

    def test_sync_on_open_skips_pull_when_push_fails(self):
        self.store.save_game(
            GameEntry(
                game_id="local-only",
                game_title="Local",
                window_title="Local Window",
            )
        )
        dialog = GameCatalogDialog.__new__(GameCatalogDialog)
        dialog.game_store = self.store
        dialog.status_label = MagicMock()
        dialog._clear_form = MagicMock()
        dialog._load_games = MagicMock()
        dialog._notify_saved = MagicMock()
        service = MagicMock()
        service.get_all_records.return_value = []
        service.append_row.return_value = False
        dialog._game_info_service = MagicMock(return_value=service)

        dialog.sync_on_open()

        self.assertEqual(service.get_all_records.call_count, 1)
        self.assertEqual(len(self.store.load_games()), 1)
        dialog._notify_saved.assert_not_called()

    def test_sync_on_close_pushes_once(self):
        dialog = GameCatalogDialog.__new__(GameCatalogDialog)
        dialog._close_sync_done = False
        dialog.status_label = MagicMock()
        dialog._push_local_games = MagicMock(
            return_value=MagicMock(sent=1, updated=1, appended=0, failed=0)
        )
        service = MagicMock()
        dialog._game_info_service = MagicMock(return_value=service)
        dialog.accept = MagicMock()

        dialog._close_dialog()
        dialog._sync_on_close()

        dialog._push_local_games.assert_called_once_with(service)
        dialog.accept.assert_called_once()


class TestGameCatalogDialogForm(unittest.TestCase):
    def test_prepare_new_game_prefills_window_title(self):
        dialog = GameCatalogDialog.__new__(GameCatalogDialog)
        dialog.game_title_edit = MagicMock()
        dialog.window_title_edit = MagicMock()
        dialog.play_with_friends_check = MagicMock()
        dialog.is_browser_game_check = MagicMock()

        dialog.prepare_new_game(window_title="  Game Window Title  ")

        dialog.game_title_edit.setText.assert_called_once_with("")
        dialog.window_title_edit.setText.assert_any_call("")
        dialog.window_title_edit.setText.assert_called_with("Game Window Title")
        dialog.play_with_friends_check.setChecked.assert_called_once_with(False)
        dialog.is_browser_game_check.setChecked.assert_called_once_with(False)


if __name__ == "__main__":
    unittest.main()

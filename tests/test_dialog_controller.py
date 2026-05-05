import unittest
from types import SimpleNamespace

from src.app.controllers.dialog import MainWindowDialogController
from src.app.dialog_state import DialogRefState


class MainWindowDialogControllerTest(unittest.TestCase):
    def test_report_dialog_reference_uses_injected_state(self):
        created = []

        class Dialog:
            def __init__(self, *_args):
                created.append(self)
                self.visible = False

            def isVisible(self):
                return self.visible

            def show(self):
                self.visible = True

            def raise_(self):
                pass

            def activateWindow(self):
                pass

        log_handler = object()
        state = DialogRefState()
        controller = MainWindowDialogController(
            parent_widget=SimpleNamespace(),
            report_dialog_cls=Dialog,
            manual_record_dialog_cls=Dialog,
            game_catalog_dialog_cls=Dialog,
            settings_dialog_cls=Dialog,
            state=state,
            has_recorder=lambda: True,
            log_handler_provider=lambda: log_handler,
            record_with_times=lambda _game, _start, _end: 0.0,
            games_provider=lambda: [],
            get_today_stats=lambda: ({}, 0.0),
            set_today_stats=lambda _minutes, _seconds: None,
            set_disabled=lambda _disabled: None,
            get_report_button=lambda: None,
            get_manual_record_button=lambda: None,
            open_report_dialog_callback=lambda: None,
            open_manual_record_dialog_callback=lambda: None,
            set_status=lambda _message: None,
            active_games_provider=lambda: [],
            update_today_totals=lambda _active, _now: 0.0,
            update_today_games_list=lambda _now: None,
            update_overtime_alert=lambda _seconds: None,
            sync_overlay=lambda: None,
            on_settings_saved_callback=lambda: None,
            on_game_catalog_saved_callback=lambda: None,
            init_components=lambda: None,
        )

        controller.open_report_dialog()

        self.assertIs(state.report_dialog, created[0])
        self.assertTrue(state.report_dialog.visible)


if __name__ == "__main__":
    unittest.main()

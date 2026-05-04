import unittest
from types import SimpleNamespace

from tests.test_stubs import install_stubs

install_stubs()

from src.app.controllers.context_menu import MainWindowContextMenuController


class MainWindowContextMenuControllerTest(unittest.TestCase):
    def _create_controller(self, calls):
        return MainWindowContextMenuController(
            parent_widget=SimpleNamespace(),
            display_modes=("小", "大"),
            display_mode_provider=lambda: "小",
            set_display_mode=lambda mode: calls.append(("mode", mode)),
            open_manual_record_dialog=lambda: calls.append("manual"),
            open_report_dialog=lambda: calls.append("report"),
            open_game_catalog_dialog=lambda: calls.append("catalog"),
            open_settings_dialog=lambda: calls.append("settings"),
            quit_application=lambda: calls.append("quit"),
        )

    def test_handle_selection_uses_injected_display_mode_callback(self):
        calls = []
        controller = self._create_controller(calls)
        selected_action = object()

        controller.handle_context_menu_selection(
            selected_action,
            report_action=object(),
            settings_action=object(),
            exit_action=object(),
            mode_actions={"大": selected_action},
        )

        self.assertEqual(calls, [("mode", "大")])

    def test_handle_selection_uses_injected_report_callback(self):
        calls = []
        controller = self._create_controller(calls)
        selected_action = object()

        controller.handle_context_menu_selection(
            selected_action,
            report_action=selected_action,
            settings_action=object(),
            exit_action=object(),
        )

        self.assertEqual(calls, ["report"])


if __name__ == "__main__":
    unittest.main()

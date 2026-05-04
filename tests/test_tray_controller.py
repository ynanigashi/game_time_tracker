import unittest
from types import SimpleNamespace

from tests.test_stubs import FakeAction, install_stubs

install_stubs()

from src.app.controllers.tray import MainWindowTrayController
from src.app.tray_state import TrayActionState


class MainWindowTrayControllerTest(unittest.TestCase):
    def test_sync_window_actions_uses_injected_action_state(self):
        action_state = TrayActionState(
            show_action=FakeAction("show"),
            hide_action=FakeAction("hide"),
        )
        controller = MainWindowTrayController(
            parent_widget=SimpleNamespace(),
            base_title="Game Time Tracker",
            action_state=action_state,
            is_window_visible=lambda: False,
        )

        controller.sync_tray_window_actions()

        self.assertTrue(action_state.show_action.visible)
        self.assertFalse(action_state.hide_action.visible)

    def test_build_tray_menu_uses_injected_action_callbacks(self):
        calls = []
        owner = SimpleNamespace(
            tray_overlay_enabled=False,
            startup_window_visible=True,
        )
        controller = MainWindowTrayController(
            parent_widget=owner,
            base_title="Game Time Tracker",
            action_state=TrayActionState(),
            get_tray_overlay_enabled=lambda: owner.tray_overlay_enabled,
            get_startup_window_visible=lambda: owner.startup_window_visible,
            show_main_window=lambda: calls.append("show"),
            open_report_dialog=lambda: calls.append("report"),
            set_startup_window_visible=lambda visible: calls.append(
                ("startup", visible)
            ),
            sync_tray_window_actions_callback=lambda: calls.append("sync"),
        )

        menu = controller.build_tray_menu()
        menu.actions[0].triggered.callback()
        menu.actions[4].triggered.callback()
        menu.menus[0].actions[1].triggered.callback()
        menu.aboutToShow.callback()

        self.assertEqual(calls, ["show", "report", ("startup", False), "sync"])

    def test_set_tray_overlay_enabled_uses_injected_persistence_callbacks(self):
        calls = []
        owner = SimpleNamespace(tray_overlay_enabled=False)
        controller = MainWindowTrayController(
            parent_widget=owner,
            base_title="Game Time Tracker",
            action_state=TrayActionState(),
            set_tray_overlay_enabled_value=lambda enabled: setattr(
                owner,
                "tray_overlay_enabled",
                enabled,
            ),
            save_window_state=lambda: calls.append("save"),
            sync_overlay=lambda: calls.append("overlay"),
        )

        controller.set_tray_overlay_enabled(True)

        self.assertTrue(owner.tray_overlay_enabled)
        self.assertEqual(calls, ["save", "overlay"])

    def test_show_main_window_from_tray_uses_injected_flow_callbacks(self):
        calls = []
        owner = SimpleNamespace(
            show=lambda: calls.append("show"),
            raise_=lambda: calls.append("raise"),
            activateWindow=lambda: calls.append("activate"),
        )
        controller = MainWindowTrayController(
            parent_widget=owner,
            base_title="Game Time Tracker",
            action_state=TrayActionState(),
            show_window=owner.show,
            raise_window=owner.raise_,
            activate_window=owner.activateWindow,
            process_pending_ui_events_callback=lambda: calls.append("process"),
            align_today_display_to_overlay_position_callback=lambda: calls.append(
                "align"
            ),
            sync_tray_window_actions_callback=lambda: calls.append("tray"),
            sync_overlay=lambda: calls.append("overlay"),
        )

        controller.show_main_window_from_tray()

        self.assertEqual(
            calls,
            [
                "show",
                "process",
                "align",
                "process",
                "align",
                "raise",
                "activate",
                "tray",
                "overlay",
            ],
        )

    def test_quit_application_uses_injected_shutdown_callbacks(self):
        calls = []
        owner = SimpleNamespace(tray_icon=None)
        controller = MainWindowTrayController(
            parent_widget=owner,
            base_title="Game Time Tracker",
            action_state=TrayActionState(),
            get_tray_icon=lambda: owner.tray_icon,
            set_quitting=lambda value: calls.append(("quitting", value)),
            record_playing_games_before_close=lambda: calls.append("record"),
            save_window_state=lambda: calls.append("save"),
            close_overlay=lambda: calls.append("close_overlay"),
        )

        controller.quit_application()

        self.assertEqual(
            calls,
            [("quitting", True), "record", "save", "close_overlay"],
        )


if __name__ == "__main__":
    unittest.main()

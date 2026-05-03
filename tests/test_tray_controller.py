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
        owner = SimpleNamespace(isVisible=lambda: False)
        controller = MainWindowTrayController(
            owner,
            base_title="Game Time Tracker",
            action_state=action_state,
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
            owner,
            base_title="Game Time Tracker",
            action_state=TrayActionState(),
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


if __name__ == "__main__":
    unittest.main()

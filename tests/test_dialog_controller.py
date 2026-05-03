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

        owner = SimpleNamespace(
            recorder=SimpleNamespace(log_handler=object()),
        )
        state = DialogRefState()
        controller = MainWindowDialogController(
            owner,
            report_dialog_cls=Dialog,
            manual_record_dialog_cls=Dialog,
            game_catalog_dialog_cls=Dialog,
            settings_dialog_cls=Dialog,
            state=state,
        )

        controller.open_report_dialog()

        self.assertIs(state.report_dialog, created[0])
        self.assertTrue(state.report_dialog.visible)


if __name__ == "__main__":
    unittest.main()

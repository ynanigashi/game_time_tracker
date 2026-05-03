import unittest

from src.app.dialog_state import DialogRefState


class DialogRefStateTest(unittest.TestCase):
    def test_defaults_to_no_dialogs_and_disconnected_buttons(self):
        state = DialogRefState()

        self.assertIsNone(state.report_dialog)
        self.assertIsNone(state.game_catalog_dialog)
        self.assertIsNone(state.manual_record_dialog)
        self.assertIsNone(state.settings_dialog)
        self.assertFalse(state.report_button_connected)
        self.assertFalse(state.manual_record_button_connected)

    def test_dialog_references_are_assignable(self):
        state = DialogRefState()
        report_dialog = object()
        manual_dialog = object()

        state.report_dialog = report_dialog
        state.manual_record_dialog = manual_dialog
        state.report_button_connected = True

        self.assertIs(state.report_dialog, report_dialog)
        self.assertIs(state.manual_record_dialog, manual_dialog)
        self.assertTrue(state.report_button_connected)


if __name__ == "__main__":
    unittest.main()

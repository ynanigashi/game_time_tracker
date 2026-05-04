import unittest

from src.ui.report_graph_unit_state import ReportGraphUnitState


class ReportGraphUnitStateTest(unittest.TestCase):
    def test_defaults_to_minutes_without_buttons(self):
        state = ReportGraphUnitState()

        self.assertFalse(state.graph_unit_hours)
        self.assertFalse(state.updating_unit_toggles)
        self.assertEqual(state.minute_buttons, [])
        self.assertEqual(state.hour_buttons, [])

    def test_button_lists_are_independent_per_instance(self):
        first = ReportGraphUnitState()
        second = ReportGraphUnitState()

        first.minute_buttons.append(object())

        self.assertEqual(second.minute_buttons, [])


if __name__ == "__main__":
    unittest.main()

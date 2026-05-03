import unittest

from src.ui.report_trend_selection_state import ReportTrendSelectionState


class ReportTrendSelectionStateTest(unittest.TestCase):
    def test_defaults_to_no_selection(self):
        state = ReportTrendSelectionState()

        self.assertIsNone(state.selected_indices)

    def test_selected_indices_are_mutable(self):
        state = ReportTrendSelectionState()

        state.selected_indices = (1, 3)

        self.assertEqual(state.selected_indices, (1, 3))


if __name__ == "__main__":
    unittest.main()

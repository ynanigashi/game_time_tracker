import unittest

from src.ui.report_title_filter_state import ReportTitleFilterState


class ReportTitleFilterStateTest(unittest.TestCase):
    def test_defaults_to_idle_uninitialized(self):
        state = ReportTitleFilterState()

        self.assertFalse(state.updating)
        self.assertFalse(state.initialized)

    def test_flags_are_mutable(self):
        state = ReportTitleFilterState()

        state.updating = True
        state.initialized = True

        self.assertTrue(state.updating)
        self.assertTrue(state.initialized)


if __name__ == "__main__":
    unittest.main()

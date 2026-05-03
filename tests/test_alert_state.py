import unittest

from src.app.alert_state import GameAlertState


class GameAlertStateTest(unittest.TestCase):
    def test_create_initializes_enabled_flag_and_tracker_thresholds(self):
        state = GameAlertState.create(
            enabled=False,
            thresholds_minutes=(45, 50),
        )

        self.assertFalse(state.overtime_alert_enabled)
        self.assertEqual(state.overtime_alert_tracker.thresholds_minutes, (45, 50))
        self.assertEqual(state.overtime_alert_tracker.alerted_threshold_minutes, set())
        self.assertFalse(state.overtime_alert_tracker.initialized)

    def test_create_copies_threshold_sequence(self):
        thresholds = [45, 50]

        state = GameAlertState.create(
            enabled=True,
            thresholds_minutes=thresholds,
        )
        thresholds.append(55)

        self.assertEqual(state.overtime_alert_tracker.thresholds_minutes, (45, 50))


if __name__ == "__main__":
    unittest.main()

import unittest
from types import SimpleNamespace

from src.ui.report_log_operation_state import ReportLogOperationState
from src.ui.report_log_operations import ReportLogOperationController


class ReportLogOperationControllerTest(unittest.TestCase):
    def test_finish_log_edit_uses_injected_debug_callback(self):
        calls = []
        owner = SimpleNamespace(
            _mark_report_data_changed=lambda: calls.append("changed"),
            refresh_logs=lambda: calls.append("refresh"),
            _mark_tab_clean=lambda tab: calls.append(("clean", tab)),
        )
        debug_messages = []
        controller = ReportLogOperationController(
            owner,
            ReportLogOperationState(),
            log_tab=2,
            set_debug_message=lambda message, **_kwargs: debug_messages.append(message),
        )

        controller.finish_log_edit(
            SimpleNamespace(local_updated=True, spreadsheet_updated=True)
        )

        self.assertEqual(calls, ["changed", "refresh", ("clean", 2)])
        self.assertEqual(debug_messages, ["ログを編集し、スプシにも反映しました"])


if __name__ == "__main__":
    unittest.main()

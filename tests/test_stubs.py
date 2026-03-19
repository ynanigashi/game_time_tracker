# pyright: reportAttributeAccessIssue=false, reportArgumentType=false
"""テスト用共通スタブ・フェイク定義.

PySide6, gspread, pygetwindow の外部依存をスタブで置き換え、
テストモジュール間で共有する。
"""

import sys
import types
from datetime import datetime
from typing import Any, Dict, List, Tuple


# =============================================================================
# PySide6 スタブ
# =============================================================================
class FakeQWidget:
    """QWidget のスタブ."""

    def closeEvent(self, event) -> None:
        pass

    def resizeEvent(self, event) -> None:
        pass

    def mousePressEvent(self, event) -> None:
        pass


class FakeQMouseEvent:
    """QMouseEvent のスタブ."""

    def button(self):
        return None


class FakeQTableWidgetItem:
    """QTableWidgetItem のスタブ."""

    def __init__(self, text: Any = "") -> None:
        self._text = "" if text is None else str(text)

    def text(self) -> str:
        return self._text

    def setText(self, text: Any) -> None:
        self._text = "" if text is None else str(text)


class FakeQApplication:
    """QApplication のスタブ."""

    @staticmethod
    def beep() -> None:
        return None


fake_pyside6_core: Any = types.SimpleNamespace(
    QTimer=type("QTimer", (), {}),
    Qt=types.SimpleNamespace(
        MouseButton=types.SimpleNamespace(LeftButton=1, RightButton=2)
    ),
)
fake_pyside6_gui: Any = types.SimpleNamespace(
    QCloseEvent=type("QCloseEvent", (), {}),
    QMouseEvent=FakeQMouseEvent,
    QResizeEvent=type("QResizeEvent", (), {}),
)
fake_pyside6_widgets: Any = types.SimpleNamespace(
    QApplication=FakeQApplication,
    QWidget=FakeQWidget,
    QTableWidgetItem=FakeQTableWidgetItem,
    QCheckBox=type("QCheckBox", (), {}),
    QPushButton=type("QPushButton", (), {}),
    QLabel=type("QLabel", (), {}),
    QListWidget=type("QListWidget", (), {}),
    QVBoxLayout=type("QVBoxLayout", (), {}),
    QHBoxLayout=type("QHBoxLayout", (), {}),
    QTableWidget=type("QTableWidget", (), {}),
    QHeaderView=type("QHeaderView", (), {}),
)


# =============================================================================
# gspread スタブ
# =============================================================================
_existing_gspread = sys.modules.get("gspread")
if _existing_gspread is None:
    fake_gspread: Any = types.SimpleNamespace(
        service_account=lambda filename=None: None,
        exceptions=types.SimpleNamespace(
            APIError=type("APIError", (Exception,), {}),
            SpreadsheetNotFound=type("SpreadsheetNotFound", (Exception,), {}),
            WorksheetNotFound=type("WorksheetNotFound", (Exception,), {}),
        ),
    )
else:
    fake_gspread = _existing_gspread
    if not hasattr(fake_gspread, "service_account"):
        fake_gspread.service_account = lambda filename=None: None
    if not hasattr(fake_gspread, "exceptions") or fake_gspread.exceptions is None:
        fake_gspread.exceptions = types.SimpleNamespace()
    if not hasattr(fake_gspread.exceptions, "APIError"):
        fake_gspread.exceptions.APIError = type("APIError", (Exception,), {})
    if not hasattr(fake_gspread.exceptions, "SpreadsheetNotFound"):
        fake_gspread.exceptions.SpreadsheetNotFound = type(
            "SpreadsheetNotFound", (Exception,), {}
        )
    if not hasattr(fake_gspread.exceptions, "WorksheetNotFound"):
        fake_gspread.exceptions.WorksheetNotFound = type(
            "WorksheetNotFound", (Exception,), {}
        )


# =============================================================================
# pygetwindow スタブ
# =============================================================================
_existing_pygetwindow = sys.modules.get("pygetwindow")
if _existing_pygetwindow is None:
    fake_pygetwindow: Any = types.SimpleNamespace(
        getAllWindows=lambda: [],
        getActiveWindow=lambda: None,
    )
else:
    fake_pygetwindow = _existing_pygetwindow
    if not hasattr(fake_pygetwindow, "getAllWindows"):
        fake_pygetwindow.getAllWindows = lambda: []
    if not hasattr(fake_pygetwindow, "getActiveWindow"):
        fake_pygetwindow.getActiveWindow = lambda: None


# =============================================================================
# sys.modules への登録
# =============================================================================
def install_stubs() -> None:
    """外部依存のスタブを sys.modules に登録する.
    
    テストモジュールの先頭（他モジュール import 前）で呼び出すこと。
    """
    sys.modules.setdefault("PySide6", types.ModuleType("PySide6"))
    sys.modules.setdefault("PySide6.QtCore", types.ModuleType("PySide6.QtCore"))
    sys.modules.setdefault("PySide6.QtGui", types.ModuleType("PySide6.QtGui"))
    sys.modules.setdefault("PySide6.QtWidgets", types.ModuleType("PySide6.QtWidgets"))

    for attr, val in vars(fake_pyside6_core).items():
        setattr(sys.modules["PySide6.QtCore"], attr, val)
    for attr, val in vars(fake_pyside6_gui).items():
        setattr(sys.modules["PySide6.QtGui"], attr, val)
    for attr, val in vars(fake_pyside6_widgets).items():
        setattr(sys.modules["PySide6.QtWidgets"], attr, val)

    if "gspread" not in sys.modules:
        sys.modules["gspread"] = fake_gspread  # type: ignore[assignment]
    else:
        # 既存モジュールの属性を補完
        mod = sys.modules["gspread"]
        for attr, val in vars(fake_gspread).items():
            if not hasattr(mod, attr):
                setattr(mod, attr, val)

    if "pygetwindow" not in sys.modules:
        sys.modules["pygetwindow"] = fake_pygetwindow  # type: ignore[assignment]
    else:
        mod = sys.modules["pygetwindow"]
        for attr, val in vars(fake_pygetwindow).items():
            if not hasattr(mod, attr):
                setattr(mod, attr, val)


# =============================================================================
# FakeLogHandler
# =============================================================================
class FakeLogHandler:
    """テスト用 LogHandler のフェイク実装."""

    def __init__(self) -> None:
        self.records: List[Dict[str, Any]] = []
        self.current_index: int = 0

    def format_datetime_to_gss_style(self, dt: datetime) -> str:
        return dt.strftime("%Y/%m/%d %H:%M:%S")

    def get_and_increment_index(self) -> int:
        self.current_index += 1
        return self.current_index

    def get_cached_records(self) -> List[Dict[str, Any]]:
        """キャッシュされたレコードを返す."""
        return self.records

    def get_today_stats(self) -> Tuple[Dict[str, float], float]:
        """今日のゲーム時間統計を取得（1回のパースで取得）."""
        from src.core.models import parse_record

        game_minutes: Dict[str, float] = {}
        total_seconds = 0.0
        today = datetime.now().date()

        try:
            for record in self.records:
                parsed = parse_record(record)
                if parsed is None or parsed.start.date() != today:
                    continue

                seconds = (parsed.end - parsed.start).total_seconds()
                total_seconds += seconds

                minutes = seconds / 60.0
                game_minutes[parsed.game_title] = (
                    game_minutes.get(parsed.game_title, 0) + minutes
                )
        except Exception as e:
            print(f"今日の統計情報の取得中にエラーが発生しました: {e}")

        return game_minutes, total_seconds

    def save_record(self, values: List[Any]) -> bool:
        """レコードを保存し、キャッシュにも追加。成功時Trueを返す。"""
        if len(values) >= 5:
            self.records.append(
                {
                    "index": values[0],
                    "start_time": values[1],
                    "end_time": values[2],
                    "title": values[3],
                    "play_with_friends": values[4],
                }
            )
        return True


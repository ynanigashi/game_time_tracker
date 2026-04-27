# pyright: reportAttributeAccessIssue=false, reportArgumentType=false
"""テスト用共通スタブ・フェイク定義.

PySide6, gspread, pygetwindow の外部依存をスタブで置き換え、
テストモジュール間で共有する。
"""

import sys
import types
from datetime import date, datetime
from typing import Any, Dict, List, Tuple


# =============================================================================
# PySide6 スタブ
# =============================================================================
class FakeQWidget:
    """QWidget のスタブ."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        pass

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

    def globalPos(self):
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

    @staticmethod
    def processEvents() -> None:
        return None


class FakeQDate:
    def __init__(self, year: int, month: int, day: int) -> None:
        self._date = date(year, month, day)

    def year(self) -> int:
        return self._date.year

    def month(self) -> int:
        return self._date.month

    def day(self) -> int:
        return self._date.day

    def toPython(self) -> date:
        return self._date


class FakeSignal:
    def connect(self, callback: Any) -> None:
        self.callback = callback

    def disconnect(self, callback: Any) -> None:
        self.callback = None


class FakeButton:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.clicked = FakeSignal()
        self.toggled = FakeSignal()

    def setCheckable(self, value: bool) -> None:
        self.checkable = value

    def setFixedSize(self, width: int, height: int) -> None:
        self.fixed_size = (width, height)

    def setMinimumWidth(self, width: int) -> None:
        self.minimum_width = width

    def setObjectName(self, name: str) -> None:
        self.object_name = name

    def isChecked(self) -> bool:
        return bool(getattr(self, "checked", False))

    def setChecked(self, value: bool) -> None:
        self.checked = value

    def setText(self, text: str) -> None:
        self.text = text

    def setStyleSheet(self, style: str) -> None:
        self.style = style

    def setEnabled(self, value: bool) -> None:
        self.enabled = value

class FakeWidget:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        pass

    def setWindowTitle(self, title: str) -> None:
        self.window_title = title

    def resize(self, width: int, height: int) -> None:
        self.size = (width, height)

    def setLayout(self, layout: Any) -> None:
        self.layout = layout

    def show(self) -> None:
        self.visible = True

    def raise_(self) -> None:
        pass

    def activateWindow(self) -> None:
        pass

    def isVisible(self) -> bool:
        return bool(getattr(self, "visible", False))

    def setEnabled(self, value: bool) -> None:
        self.enabled = value

    def accept(self) -> None:
        self.accepted = True

    def reject(self) -> None:
        self.rejected = True


class FakeLineEdit(FakeWidget):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._text = ""

    def setText(self, text: Any) -> None:
        self._text = "" if text is None else str(text)

    def text(self) -> str:
        return self._text


class FakeTextEdit(FakeWidget):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._text = ""

    def setPlainText(self, text: Any) -> None:
        self._text = "" if text is None else str(text)

    def toPlainText(self) -> str:
        return self._text


class FakeDateEdit(FakeWidget):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._date = FakeQDate(2000, 1, 1)

    def setCalendarPopup(self, value: bool) -> None:
        self.calendar_popup = value

    def setDisplayFormat(self, value: str) -> None:
        self.display_format = value

    def setDate(self, value: Any) -> None:
        self._date = value

    def date(self) -> Any:
        return self._date


class FakeComboBox(FakeWidget):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.items: List[Tuple[str, Any]] = []
        self.current_index = -1
        self.currentIndexChanged = FakeSignal()

    def addItem(self, text: str, user_data: Any = None) -> None:
        self.items.append((text, user_data))
        if self.current_index < 0:
            self.current_index = 0

    def findData(self, data: Any) -> int:
        for index, item in enumerate(self.items):
            if item[1] == data:
                return index
        return -1

    def setCurrentIndex(self, index: int) -> None:
        self.current_index = index

    def currentData(self) -> Any:
        if 0 <= self.current_index < len(self.items):
            return self.items[self.current_index][1]
        return None


class FakeTableWidget(FakeWidget):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.itemSelectionChanged = FakeSignal()
        self.row_count = 0
        self.column_count = 0
        self.items: Dict[Tuple[int, int], Any] = {}
        self.current_row = -1

    def setColumnCount(self, count: int) -> None:
        self.column_count = count

    def setHorizontalHeaderLabels(self, labels: List[str]) -> None:
        self.header_labels = labels

    def setColumnHidden(self, column: int, hidden: bool) -> None:
        self.hidden_column = (column, hidden)

    def setRowCount(self, count: int) -> None:
        self.row_count = count
        if count == 0:
            self.current_row = -1

    def setItem(self, row: int, column: int, item: Any) -> None:
        self.items[(row, column)] = item
        if self.current_row < 0:
            self.current_row = row

    def item(self, row: int, column: int) -> Any:
        return self.items.get((row, column))

    def currentRow(self) -> int:
        return self.current_row


class FakeLabel(FakeWidget):
    def __init__(self, text: Any = "", *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._text = "" if text is None else str(text)

    def setText(self, text: Any) -> None:
        self._text = "" if text is None else str(text)

    def text(self) -> str:
        return self._text


class FakeLayout:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.items = []

    def addRow(self, *args: Any) -> None:
        self.items.append(args)

    def addLayout(self, *args: Any) -> None:
        self.items.append(args)

    def addWidget(self, *args: Any) -> None:
        self.items.append(args)

    def addSpacing(self, *args: Any) -> None:
        self.items.append(args)

    def addStretch(self, *args: Any) -> None:
        self.items.append(args)

    def setContentsMargins(self, *args: Any) -> None:
        self.contents_margins = args

    def setSpacing(self, spacing: int) -> None:
        self.spacing = spacing


class FakeDialogButtonBox(FakeWidget):
    StandardButton = types.SimpleNamespace(Save=1, Cancel=2)

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.accepted = FakeSignal()
        self.rejected = FakeSignal()


class FakeMessageBox:
    @staticmethod
    def warning(*args: Any, **kwargs: Any) -> None:
        return None


class FakeFileDialog:
    next_open_file_name = ("", "")
    next_save_file_name = ("", "")

    @staticmethod
    def getOpenFileName(*args: Any, **kwargs: Any) -> Tuple[str, str]:
        return FakeFileDialog.next_open_file_name

    @staticmethod
    def getSaveFileName(*args: Any, **kwargs: Any) -> Tuple[str, str]:
        return FakeFileDialog.next_save_file_name


class FakeMenu:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.actions = []
        self.menus = []
        self.selected_action = None

    def addAction(self, text: str) -> object:
        action = types.SimpleNamespace(
            text=text,
            checkable=False,
            checked=False,
        )
        action.setCheckable = lambda value: setattr(action, "checkable", value)
        action.setChecked = lambda value: setattr(action, "checked", value)
        self.actions.append(action)
        return action

    def addMenu(self, text: str) -> "FakeMenu":
        menu = FakeMenu()
        menu.text = text
        self.menus.append(menu)
        return menu

    def exec(self, position: Any) -> object:
        return self.selected_action

fake_pyside6_core: Any = types.SimpleNamespace(
    QDate=FakeQDate,
    QTimer=type("QTimer", (), {}),
    Qt=types.SimpleNamespace(
        MouseButton=types.SimpleNamespace(LeftButton=1, RightButton=2),
        ContextMenuPolicy=types.SimpleNamespace(CustomContextMenu=3),
        CheckState=types.SimpleNamespace(Unchecked=0, Checked=2),
        AlignmentFlag=types.SimpleNamespace(AlignCenter=0),
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
    QCheckBox=FakeButton,
    QPushButton=FakeButton,
    QLabel=FakeLabel,
    QFileDialog=FakeFileDialog,
    QListWidget=type("QListWidget", (), {}),
    QDialog=FakeWidget,
    QDialogButtonBox=FakeDialogButtonBox,
    QFormLayout=FakeLayout,
    QLineEdit=FakeLineEdit,
    QMessageBox=FakeMessageBox,
    QTextEdit=FakeTextEdit,
    QComboBox=FakeComboBox,
    QDateEdit=FakeDateEdit,
    QTabWidget=FakeWidget,
    QAbstractItemView=type(
        "QAbstractItemView",
        (),
        {
            "EditTrigger": types.SimpleNamespace(NoEditTriggers=0),
            "SelectionBehavior": types.SimpleNamespace(SelectRows=1),
        },
    ),
    QVBoxLayout=FakeLayout,
    QHBoxLayout=FakeLayout,
    QTableWidget=FakeTableWidget,
    QHeaderView=type("QHeaderView", (), {}),
    QMenu=FakeMenu,
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

    def get_report_stats(self, *, start_date=None, end_date=None):
        from src.core.reporting import build_game_report

        return build_game_report(
            self.records,
            start_date=start_date,
            end_date=end_date,
        )

    def get_trend_stats(self, *, granularity, start_date=None, end_date=None):
        from src.core.reporting import build_play_time_trend

        return build_play_time_trend(
            self.records,
            granularity=granularity,
            start_date=start_date,
            end_date=end_date,
        )

    def get_trend_stats_by_title(
        self,
        *,
        granularity,
        titles=None,
        start_date=None,
        end_date=None,
    ):
        from src.core.reporting import build_play_time_trend_by_title

        return build_play_time_trend_by_title(
            self.records,
            granularity=granularity,
            titles=titles,
            start_date=start_date,
            end_date=end_date,
        )

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

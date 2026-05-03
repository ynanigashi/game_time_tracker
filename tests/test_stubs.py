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
        self.visible = False
        self._geom = types.SimpleNamespace(
            x=lambda: 0,
            y=lambda: 0,
            width=lambda: 100,
            height=lambda: 30,
        )

    def show(self) -> None:
        self.visible = True

    def hide(self) -> None:
        self.visible = False

    def isVisible(self) -> bool:
        return bool(getattr(self, "visible", False))

    def raise_(self) -> None:
        pass

    def activateWindow(self) -> None:
        pass

    def geometry(self) -> Any:
        return self._geom

    def setGeometry(self, x: int, y: int, width: int, height: int) -> None:
        self._geom = types.SimpleNamespace(
            x=lambda: x,
            y=lambda: y,
            width=lambda: width,
            height=lambda: height,
        )

    def move(self, x: int, y: int) -> None:
        self.setGeometry(x, y, int(self._geom.width()), int(self._geom.height()))

    def resize(self, width: int, height: int) -> None:
        self.setGeometry(int(self._geom.x()), int(self._geom.y()), width, height)

    def width(self) -> int:
        return int(self._geom.width())

    def height(self) -> int:
        return int(self._geom.height())

    def closeEvent(self, event) -> None:
        pass

    def moveEvent(self, event) -> None:
        pass

    def nativeEvent(self, event_type, message):
        return False, 0

    def resizeEvent(self, event) -> None:
        pass

    def mousePressEvent(self, event) -> None:
        pass

    def mouseMoveEvent(self, event) -> None:
        pass

    def mouseReleaseEvent(self, event) -> None:
        pass

    def setCursor(self, cursor: Any) -> None:
        self.cursor = cursor

    def unsetCursor(self) -> None:
        self.cursor = None

    def setStyleSheet(self, style: str) -> None:
        self.style = style

    def close(self) -> bool:
        self.closed = True
        return True

    def setWindowFlags(self, flags: Any) -> None:
        self.window_flags = flags

    def setWindowOpacity(self, opacity: float) -> None:
        self.window_opacity = opacity

    def setAttribute(self, attribute: Any, enabled: bool = True) -> None:
        self.attribute = (attribute, enabled)

    def setFocusPolicy(self, policy: Any) -> None:
        self.focus_policy = policy

    def setLayout(self, layout: Any) -> None:
        self.layout = layout


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

    _instance = None

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        FakeQApplication._instance = self
        self.quit_on_last_window_closed = True
        self.quit_called = False

    @staticmethod
    def mouseButtons() -> int:
        return 0

    @staticmethod
    def style() -> Any:
        return FakeStyle()

    @staticmethod
    def instance() -> Any:
        return FakeQApplication._instance

    def setQuitOnLastWindowClosed(self, value: bool) -> None:
        self.quit_on_last_window_closed = value

    def quit(self) -> None:
        self.quit_called = True

    def exec(self) -> int:
        return 0


class FakePoint:
    def __init__(self, x: int = 0, y: int = 0) -> None:
        self._x = x
        self._y = y

    def x(self) -> int:
        return self._x

    def y(self) -> int:
        return self._y


class FakeQCursor:
    _pos = FakePoint()

    @staticmethod
    def pos() -> FakePoint:
        return FakeQCursor._pos


class FakeQIcon:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.args = args
        self.kwargs = kwargs


class FakeStyle:
    def standardIcon(self, *args: Any, **kwargs: Any) -> FakeQIcon:
        return FakeQIcon()


class FakeQStyle:
    StandardPixmap = types.SimpleNamespace(SP_ComputerIcon=1)


class FakeSystemTrayIcon:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.visible = False
        self.context_menu = None

    @staticmethod
    def isSystemTrayAvailable() -> bool:
        return True

    def setToolTip(self, text: str) -> None:
        self.tooltip = text

    def setContextMenu(self, menu: Any) -> None:
        self.context_menu = menu

    def show(self) -> None:
        self.visible = True

    def hide(self) -> None:
        self.visible = False


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
    def __init__(self) -> None:
        self.callback = None

    def connect(self, callback: Any) -> None:
        self.callback = callback

    def disconnect(self, callback: Any) -> None:
        self.callback = None


class FakeTimer:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.timeout = FakeSignal()
        self.active = False
        self.interval = 0

    def setInterval(self, value: int) -> None:
        self.interval = value

    def start(self) -> None:
        self.active = True

    def stop(self) -> None:
        self.active = False

    def isActive(self) -> bool:
        return self.active

    def deleteLater(self) -> None:
        self.deleted_later = True


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

    def closeEvent(self, event) -> None:
        self.closed_event = event

    def mousePressEvent(self, event) -> None:
        pass

    def mouseMoveEvent(self, event) -> None:
        pass

    def mouseReleaseEvent(self, event) -> None:
        pass

    def setFixedWidth(self, width: int) -> None:
        self.fixed_width = width

    def setStyleSheet(self, style: str) -> None:
        self.style = style

    def setAlignment(self, alignment: Any) -> None:
        self.alignment = alignment

    def setCursor(self, cursor: Any) -> None:
        self.cursor = cursor

    def unsetCursor(self) -> None:
        self.cursor = None


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

    def clear(self) -> None:
        self.items = []
        self.current_index = -1

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

    def currentText(self) -> str:
        if 0 <= self.current_index < len(self.items):
            return self.items[self.current_index][0]
        return ""


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

    def rowCount(self) -> int:
        return self.row_count

    def setItem(self, row: int, column: int, item: Any) -> None:
        self.items[(row, column)] = item
        if self.current_row < 0:
            self.current_row = row

    def item(self, row: int, column: int) -> Any:
        return self.items.get((row, column))

    def currentRow(self) -> int:
        return self.current_row


class FakeTabWidget(FakeWidget):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.currentChanged = FakeSignal()
        self.tabs: List[Tuple[Any, str]] = []
        self.current_index = 0

    def addTab(self, widget: Any, label: str) -> None:
        self.tabs.append((widget, label))

    def currentIndex(self) -> int:
        return self.current_index

    def setCurrentIndex(self, index: int) -> None:
        self.current_index = index
        if self.currentChanged.callback is not None:
            self.currentChanged.callback(index)


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
    StandardButton = types.SimpleNamespace(Yes=1, No=2)

    @staticmethod
    def warning(*args: Any, **kwargs: Any) -> None:
        return None

    @staticmethod
    def question(*args: Any, **kwargs: Any) -> int:
        return FakeMessageBox.StandardButton.Yes


class FakeFileDialog:
    next_open_file_name = ("", "")
    next_save_file_name = ("", "")

    @staticmethod
    def getOpenFileName(*args: Any, **kwargs: Any) -> Tuple[str, str]:
        return FakeFileDialog.next_open_file_name

    @staticmethod
    def getSaveFileName(*args: Any, **kwargs: Any) -> Tuple[str, str]:
        return FakeFileDialog.next_save_file_name


class FakeAction:
    def __init__(self, text: str) -> None:
        self.text = text
        self.checkable = False
        self.checked = False
        self.visible = True
        self.triggered = FakeSignal()
        self.toggled = FakeSignal()

    def setCheckable(self, value: bool) -> None:
        self.checkable = value

    def setChecked(self, value: bool) -> None:
        self.checked = value

    def setVisible(self, value: bool) -> None:
        self.visible = value


class FakeMenu:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.actions = []
        self.menus = []
        self.selected_action = None
        self.aboutToShow = FakeSignal()

    def addAction(self, text: str) -> object:
        action = FakeAction(text)
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
    QTimer=FakeTimer,
    Qt=types.SimpleNamespace(
        MouseButton=types.SimpleNamespace(LeftButton=1, RightButton=2),
        ContextMenuPolicy=types.SimpleNamespace(CustomContextMenu=3),
        CheckState=types.SimpleNamespace(Unchecked=0, Checked=2),
        AlignmentFlag=types.SimpleNamespace(AlignCenter=0),
        CursorShape=types.SimpleNamespace(
            OpenHandCursor=10,
            ClosedHandCursor=11,
            SizeAllCursor=12,
        ),
    ),
)
fake_pyside6_gui: Any = types.SimpleNamespace(
    QCloseEvent=type("QCloseEvent", (), {}),
    QCursor=FakeQCursor,
    QIcon=FakeQIcon,
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
    QStyle=FakeQStyle,
    QSystemTrayIcon=FakeSystemTrayIcon,
    QTextEdit=FakeTextEdit,
    QComboBox=FakeComboBox,
    QDateEdit=FakeDateEdit,
    QTabWidget=FakeTabWidget,
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

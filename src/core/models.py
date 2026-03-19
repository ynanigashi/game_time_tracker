"""データモデル定義."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Sequence, Tuple

from src.core.text_utils import normalize_title
from src.core.time_utils import GSS_DATETIME_FORMAT


@dataclass
class GameEntry:
    """ゲーム情報を保持するデータクラス."""

    game_title: str
    window_title: str
    play_with_friends: bool = False
    is_browser_game: bool = False
    is_playing: bool = field(default=False, compare=False)
    start_time: Optional[datetime] = field(default=None, compare=False)
    inactive_since: Optional[datetime] = field(default=None, compare=False)
    _normalized_window_title: Optional[str] = field(default=None, init=False, repr=False, compare=False)

    def __setattr__(self, name: str, value: object) -> None:
        """Invalidate title cache when `window_title` changes."""
        object.__setattr__(self, name, value)
        if name == "window_title":
            object.__setattr__(self, "_normalized_window_title", None)

    def _get_normalized_window_title(self) -> str:
        """Return cached normalized `window_title`."""
        if self._normalized_window_title is None:
            self._normalized_window_title = normalize_title(self.window_title)
        return self._normalized_window_title

    def matches_window(self, window_title: str, browsers: Sequence[str]) -> bool:
        """Check whether this game matches a normalized window title.

        Args:
            window_title: Normalized window title.
            browsers: Normalized browser name list.
        """
        normalized_window = window_title
        normalized_target = self._get_normalized_window_title()
        if not normalized_target or normalized_target not in normalized_window:
            return False

        is_browser = any(browser in normalized_window for browser in browsers)

        # Browser games should match browser windows as well.
        if self.is_browser_game:
            return True

        # Non-browser games are ignored when the title is a browser window.
        return not is_browser

    def start_session(self) -> None:
        """ゲームセッションを開始."""
        self.is_playing = True
        self.start_time = datetime.now()
        self.inactive_since = None

    def end_session(self) -> Tuple[Optional[datetime], Optional[datetime]]:
        """ゲームセッションを終了し、開始・終了時刻を返す."""
        start_time = self.start_time
        end_time = datetime.now() if start_time else None
        self.is_playing = False
        self.start_time = None
        self.inactive_since = None
        return start_time, end_time

    def set_inactive(self) -> None:
        """非アクティブ状態に設定."""
        if self.inactive_since is None:
            self.inactive_since = datetime.now()

    def set_active(self) -> None:
        """アクティブ状態に戻す（非アクティブ時間をクリア）."""
        self.inactive_since = None

    def is_inactive(self) -> bool:
        """非アクティブ状態かどうか."""
        return self.inactive_since is not None

    def get_inactive_seconds(self) -> float:
        """非アクティブ経過秒数を取得."""
        if self.inactive_since is None:
            return 0.0
        return (datetime.now() - self.inactive_since).total_seconds()


@dataclass
class ParsedRecord:
    """パース済みレコードを保持するデータクラス."""

    start: datetime
    end: datetime
    game_title: str


def parse_record(record: dict) -> Optional[ParsedRecord]:
    """レコードをパースしてParsedRecordを返す。パース失敗時はNone."""
    try:
        start = datetime.strptime(str(record['start_time']), GSS_DATETIME_FORMAT)
        end = datetime.strptime(str(record['end_time']), GSS_DATETIME_FORMAT)
        game_title = str(record.get('title', '不明'))
        return ParsedRecord(start=start, end=end, game_title=game_title)
    except (ValueError, KeyError):
        return None


def parse_bool(value: object) -> bool:
    """文字列を bool に変換."""
    return str(value).upper() == 'TRUE'

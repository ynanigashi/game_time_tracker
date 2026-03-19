"""ビジネスロジック - ゲーム情報ローダー、ウィンドウスキャナー、セッション記録、統計追跡."""

import logging
from datetime import datetime
from typing import List, Optional, Sequence

import gspread
import pygetwindow as gw

from src.core.models import GameEntry, parse_bool
from src.core.services_domain import (
    DailyStatsTracker,
    GameStateTracker,
    MIN_PLAY_MINUTES,
    ScanResult,
)
from src.core.time_utils import SECONDS_PER_MINUTE, split_by_day
from src.infra.config_loader import Config
from src.infra.gspread_service import GspreadService
from src.infra.log_handler import LogHandler

logger = logging.getLogger("services")


class Messages:
    """ユーザー向けメッセージ定義."""

    GAME_RECORDED = '{game_title}のプレイ時間を記録しました'
    GAME_TOO_SHORT = '{game_title}のプレイ時間が{min_minutes}分未満のため、記録されませんでした'
    NO_GAME_PLAYING = 'ゲームをプレイしていません'


class GameInfoLoader:
    """スプレッドシートからゲーム情報を読み込むクラス."""

    def __init__(self, config: Config) -> None:
        self.config = config

    def load(self) -> List[GameEntry]:
        """ゲーム情報をスプレッドシートから読み込む."""
        try:
            gspread_service = GspreadService(
                cert_file_path=self.config.log_handler.cert_file_path,
                sheet_key=self.config.game_info.sheet_key,
                sheet_gid=self.config.game_info.sheet_gid,
            )
            records = gspread_service.get_all_records()
        except FileNotFoundError as e:
            logger.error('認証情報ファイルが見つかりません: %s', e)
            return []
        except (
            gspread.exceptions.SpreadsheetNotFound,
            gspread.exceptions.WorksheetNotFound,
            gspread.exceptions.APIError,
        ) as e:
            logger.error('ゲーム情報の読み込みに失敗しました: %s', e)
            return []
        except Exception:
            logger.exception('ゲーム情報の読み込みで予期しない例外が発生しました')
            raise

        return [self._record_to_entry(record) for record in records]

    @staticmethod
    def _record_to_entry(record: dict) -> GameEntry:
        """スプレッドシートのレコードを GameEntry に変換."""
        window_title = str(record['window_title'])
        if not window_title.strip():
            logger.warning(
                "window_title が空のゲーム情報を読み込みました: game_title=%r",
                record.get('game_title', ''),
            )
        return GameEntry(
            game_title=str(record['game_title']),
            window_title=window_title,
            play_with_friends=parse_bool(record.get('play_with_friends', 'FALSE')),
            is_browser_game=parse_bool(record.get('is_browser_game', 'FALSE')),
        )


class WindowScanner:
    """アクティブなウィンドウタイトルを取得するクラス."""

    def __init__(self, excluded_titles: Sequence[str]) -> None:
        self.excluded_titles = set(excluded_titles)

    def get_titles(self) -> List[str]:
        """除外リストを考慮してウィンドウタイトルを取得."""
        titles = {
            window.title
            for window in gw.getAllWindows()
            if window.title and window.title not in self.excluded_titles
        }
        return list(titles)

    def get_foreground_title(self) -> Optional[str]:
        """フォアグラウンド（最前面）ウィンドウのタイトルを取得.

        Returns:
            フォアグラウンドウィンドウのタイトル。取得できない場合はNone。
        """
        try:
            active_window = gw.getActiveWindow()
            if active_window and active_window.title:
                return active_window.title
        except Exception:
            # pygetwindowの内部エラーは無視（ウィンドウが存在しない場合など）
            pass
        return None


class SessionRecorder:
    """ゲームセッションをスプレッドシートに記録するクラス."""

    def __init__(
        self,
        log_handler: LogHandler,
        min_play_minutes: int = MIN_PLAY_MINUTES,
    ) -> None:
        self.log_handler = log_handler
        self.min_play_minutes = min_play_minutes

    def record(self, game: GameEntry) -> Optional[float]:
        """ゲームセッションを終了して記録。日を跨いだ場合は分割。

        Returns:
            当日分のみの記録秒数。書き込み失敗時はNone。
        """
        start_time, end_time = game.end_session()

        if start_time is None or end_time is None:
            return None

        return self._record_segments(game, start_time, end_time)

    def record_with_times(
        self,
        game: GameEntry,
        start_time: datetime,
        end_time: datetime,
    ) -> Optional[float]:
        """指定された開始・終了時刻でセッションを記録。日を跨いだ場合は分割。

        ゲームの状態（is_playing, start_time）は変更しない。

        Returns:
            当日分のみの記録秒数。5分未満や書き込み失敗など保存が一件も発生しない場合はNone。
        """
        return self._record_segments(game, start_time, end_time)

    def _record_segments(
        self,
        game: GameEntry,
        start_time: datetime,
        end_time: datetime,
    ) -> Optional[float]:
        """セグメント分割と記録の共通ロジック.

        Returns:
            当日分のみの記録秒数。保存が一件も発生しない場合はNone。
        """
        today = datetime.now().date()
        today_seconds = 0.0
        any_saved = False
        segments = split_by_day(start_time, end_time)

        for seg_start, seg_end in segments:
            play_minutes = (seg_end - seg_start).total_seconds() / SECONDS_PER_MINUTE
            if play_minutes >= self.min_play_minutes:
                success = self._save_to_spreadsheet(game, seg_start, seg_end)
                if success:
                    any_saved = True
                    # 当日分のみ加算
                    if seg_start.date() == today:
                        today_seconds += (seg_end - seg_start).total_seconds()
                    logger.info(Messages.GAME_RECORDED.format(
                        game_title=game.game_title))
                else:
                    logger.warning('%sの記録保存に失敗しました', game.game_title)
            else:
                logger.debug(Messages.GAME_TOO_SHORT.format(
                    game_title=game.game_title,
                    min_minutes=self.min_play_minutes,
                ))

        return today_seconds if any_saved else None

    def _save_to_spreadsheet(
        self,
        game: GameEntry,
        start_time: datetime,
        end_time: datetime,
    ) -> bool:
        """スプレッドシートに記録を保存.

        Returns:
            保存成功時True、失敗時False。
        """
        return self.log_handler.save_record([
            self.log_handler.get_and_increment_index(),
            self.log_handler.format_datetime_to_gss_style(start_time),
            self.log_handler.format_datetime_to_gss_style(end_time),
            game.game_title,
            game.play_with_friends,
        ])

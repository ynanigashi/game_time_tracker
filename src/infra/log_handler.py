"""ログハンドラー - スプレッドシートの読み書きを担当."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Tuple

from src.core.time_utils import GSS_DATETIME_FORMAT, SECONDS_PER_MINUTE
from src.infra.config_loader import LogHandlerConfig
from src.infra.gspread_service import GspreadService

logger = logging.getLogger(__name__)


class LogHandler:
    """スプレッドシートの読み書きを担当するクラス."""

    gspread_service: GspreadService
    records: List[Dict[str, Any]]
    index: int

    def __init__(self, config: LogHandlerConfig) -> None:
        """スプレッドシートに接続し、全レコードをキャッシュに保存.
        
        Args:
            config: ログハンドラー設定（認証情報パスとシートキー）

        Raises:
            FileNotFoundError: 認証情報ファイルが存在しない場合
            gspread.exceptions.SpreadsheetNotFound: スプレッドシートが見つからない場合
            gspread.exceptions.APIError: APIエラーが発生した場合
        """
        self.gspread_service = GspreadService(
            cert_file_path=config.cert_file_path,
            sheet_key=config.sheet_key,
        )
        self.records = self.get_all_records()
        self.index = len(self.records)

    def get_all_records(self) -> List[Dict[str, Any]]:
        """全レコードをスプレッドシートから取得."""
        return self.gspread_service.get_all_records()

    def get_and_increment_index(self) -> int:
        """インデックスを取得して+1."""
        self.index += 1
        return self.index

    @staticmethod
    def format_datetime_to_gss_style(dt: datetime) -> str:
        """datetimeをスプレッドシート形式に変換."""
        return dt.strftime(GSS_DATETIME_FORMAT)

    def get_cached_records(self) -> List[Dict[str, Any]]:
        """キャッシュされたレコードを返す（スプレッドシートにアクセスしない）."""
        return self.records

    def get_today_stats(self) -> Tuple[Dict[str, float], float]:
        """今日のゲーム時間統計を取得（1回のパースで取得）.
        
        Returns:
            (game_minutes, total_seconds): 
                - game_minutes: ゲームタイトルごとの分数の辞書
                - total_seconds: 今日の完了プレイ時間の合計（秒）
        """
        from models import parse_record
        
        game_minutes: Dict[str, float] = {}
        total_seconds = 0.0
        parse_failed_count = 0
        today = datetime.now().date()
        
        try:
            for record in self.records:
                parsed = parse_record(record)
                if parsed is None:
                    parse_failed_count += 1
                    continue
                if parsed.start.date() != today:
                    continue
                
                seconds = (parsed.end - parsed.start).total_seconds()
                total_seconds += seconds
                
                minutes = seconds / SECONDS_PER_MINUTE
                game_minutes[parsed.game_title] = game_minutes.get(parsed.game_title, 0) + minutes
        except Exception as e:
            logger.error(f'今日の統計情報の取得中にエラーが発生しました: {e}')
        if parse_failed_count:
            logger.debug(
                "get_today_stats: parseに失敗したレコードをスキップしました (count=%s)",
                parse_failed_count,
            )
        
        return game_minutes, total_seconds

    def save_record(self, values: List[Any]) -> bool:
        """レコードをスプレッドシートに保存。
        
        Args:
            values: [index, start_time, end_time, title, play_with_friends] の形式。
        
        Returns:
            保存成功時True、失敗時False。
        """
        success = self.gspread_service.append_row(values)
        if success:
            # ローカルキャッシュにも追加（スプレッドシート再読込を避ける）
            if len(values) >= 5:
                self.records.append({
                    'index': values[0],
                    'start_time': values[1],
                    'end_time': values[2],
                    'title': values[3],
                    'play_with_friends': values[4],
                })
        return success

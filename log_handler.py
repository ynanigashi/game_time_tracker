"""ログハンドラー - スプレッドシートの読み書きを担当."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List

# https://docs.gspread.org/en/v5.12.1/
import gspread

if TYPE_CHECKING:
    from gspread.worksheet import Worksheet

from config_loader import ConfigLoader


class LogHandler:
    """スプレッドシートの読み書きを担当するクラス."""

    sheet: "Worksheet"
    records: List[Dict[str, Any]]
    index: int

    def __init__(self) -> None:
        """スプレッドシートに接続し、全レコードをキャッシュに保存.
        
        Raises:
            FileNotFoundError: 認証情報ファイルが存在しない場合
            gspread.exceptions.SpreadsheetNotFound: スプレッドシートが見つからない場合
            gspread.exceptions.APIError: APIエラーが発生した場合
        """
        config = ConfigLoader()
        gc = gspread.service_account(filename=Path(config.log_handler['cert_file_path']))
        self.sheet = gc.open_by_key(config.log_handler['sheet_key']).sheet1
        self.records = self.get_all_records()
        self.index = len(self.records)

    def get_all_records(self) -> List[Dict[str, Any]]:
        """全レコードをスプレッドシートから取得."""
        return self.sheet.get_all_records()

    def get_and_increment_index(self) -> int:
        """インデックスを取得して+1."""
        self.index += 1
        return self.index

    def format_datetime_to_gss_style(self, dt: datetime) -> str:
        """datetimeをスプレッドシート形式に変換."""
        return dt.strftime("%Y/%m/%d %H:%M:%S")

    def get_cached_records(self) -> List[Dict[str, Any]]:
        """キャッシュされたレコードを返す（スプレッドシートにアクセスしない）."""
        return self.records

    def save_record(self, values: List[Any]) -> bool:
        """レコードをスプレッドシートに保存。
        
        Args:
            values: [index, start_time, end_time, title, play_with_friends] の形式。
        
        Returns:
            保存成功時True、失敗時False。
        """
        try:
            self.sheet.append_row(values, value_input_option='USER_ENTERED')
            # ローカルキャッシュにも追加（スプレッドシート再読込を避ける）
            if len(values) >= 5:
                self.records.append({
                    'index': values[0],
                    'start_time': values[1],
                    'end_time': values[2],
                    'title': values[3],
                    'play_with_friends': values[4],
                })
            return True
        except gspread.exceptions.APIError as e:
            print(f'APIError occurred while appending row: {e}')
            return False
        except Exception as e:
            print(f'Exception occurred while appending row: {e}')
            return False

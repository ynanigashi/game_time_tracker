"""Google Spreadsheetサービスのラッパー."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

import gspread

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from gspread.worksheet import Worksheet


class GspreadService:
    """Google Spreadsheet操作を抽象化するサービスクラス.

    スプレッドシートへの接続、読み込み、書き込みを一元管理し、
    例外処理を統一する。
    """

    def __init__(self, cert_file_path: str, sheet_key: str, *,
                 sheet_gid: Optional[int] = None) -> None:
        """Google Spreadsheetに接続.

        Args:
            cert_file_path: サービスアカウント認証情報ファイルのパス
            sheet_key: スプレッドシートのキー
            sheet_gid: ワークシートのGID（省略時はsheet1に接続）

        Raises:
            FileNotFoundError: 認証情報ファイルが存在しない場合
            gspread.exceptions.SpreadsheetNotFound: スプレッドシートが見つからない場合
            gspread.exceptions.WorksheetNotFound: 指定したGIDのワークシートが見つからない場合
            gspread.exceptions.APIError: APIエラーが発生した場合
        """
        self.cert_file_path = cert_file_path
        self.sheet_key = sheet_key
        self.sheet_gid = sheet_gid
        self._sheet: Optional["Worksheet"] = None
        self._connect()

    def _connect(self) -> None:
        """スプレッドシートに接続."""
        gc = gspread.service_account(filename=Path(self.cert_file_path))
        spreadsheet = gc.open_by_key(self.sheet_key)
        if self.sheet_gid is not None:
            self._sheet = spreadsheet.get_worksheet_by_id(self.sheet_gid)
        else:
            self._sheet = spreadsheet.sheet1

    @property
    def sheet(self) -> "Worksheet":
        """ワークシートオブジェクトを取得."""
        if self._sheet is None:
            raise RuntimeError("Spreadsheet is not connected")
        return self._sheet

    def get_all_records(self) -> List[Dict[str, Any]]:
        """全レコードをスプレッドシートから取得.

        Returns:
            レコードのリスト（辞書形式）

        Raises:
            gspread.exceptions.APIError: API呼び出しに失敗した場合
        """
        return self.sheet.get_all_records()

    def append_row(self, values: List[Any]) -> bool:
        """行をスプレッドシートに追加.

        Args:
            values: 追加する値のリスト

        Returns:
            成功時True、失敗時False
        """
        try:
            self.sheet.append_row(values, value_input_option='USER_ENTERED')
            return True
        except gspread.exceptions.APIError as e:
            logger.error('APIエラーが発生しました: %s', e)
            return False
        except Exception as e:
            logger.error('行の追加中に例外が発生しました: %s', e)
            return False

    def update_row_by_record_id(self, record_id: str, values: List[Any]) -> bool:
        """Update a row whose record_id column matches the given value."""
        return self.update_row_by_key("record_id", record_id, values)

    def delete_row_by_record_id(self, record_id: str) -> bool:
        """Delete a row whose record_id column matches the given value."""
        return self.delete_row_by_key("record_id", record_id)

    def update_row_by_key(
        self,
        key_column: str,
        key_value: str,
        values: List[Any],
    ) -> bool:
        """Update a row whose key column matches the given value."""
        try:
            rows = self.sheet.get_all_values()
            if not rows:
                return False
            header = [str(value).strip() for value in rows[0]]
            try:
                key_col = header.index(key_column)
            except ValueError:
                return False

            for row_number, row in enumerate(rows[1:], start=2):
                if key_col < len(row) and str(row[key_col]) == key_value:
                    last_column = self._column_name(len(values))
                    self.sheet.update(
                        range_name=f"A{row_number}:{last_column}{row_number}",
                        values=[values],
                        value_input_option="USER_ENTERED",
                    )
                    return True
            return False
        except gspread.exceptions.APIError as e:
            logger.error('APIエラーが発生しました: %s', e)
            return False
        except Exception as e:
            logger.error('行の更新中に例外が発生しました: %s', e)
            return False

    def delete_row_by_key(
        self,
        key_column: str,
        key_value: str,
    ) -> bool:
        """Delete a row whose key column matches the given value.

        Missing rows are treated as success so delete operations are idempotent.
        """
        try:
            rows = self.sheet.get_all_values()
            if not rows:
                return True
            header = [str(value).strip() for value in rows[0]]
            try:
                key_col = header.index(key_column)
            except ValueError:
                return False

            for row_number, row in enumerate(rows[1:], start=2):
                if key_col < len(row) and str(row[key_col]) == key_value:
                    self.sheet.delete_rows(row_number)
                    return True
            return True
        except gspread.exceptions.APIError as e:
            logger.error("API error occurred while deleting row: %s", e)
            return False
        except Exception as e:
            logger.error("Exception occurred while deleting row: %s", e)
            return False

    @staticmethod
    def _column_name(index: int) -> str:
        """Return the 1-based spreadsheet column name."""
        name = ""
        while index > 0:
            index, remainder = divmod(index - 1, 26)
            name = chr(ord("A") + remainder) + name
        return name or "A"

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

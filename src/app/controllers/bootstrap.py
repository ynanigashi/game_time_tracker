"""MainWindow bootstrap dependency construction."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

from src.core.adapters import GameInfoLoader, SessionRecorder, WindowScanner
from src.core.domain import DailyStatsTracker, GameStateTracker
from src.core.models import GameEntry
from src.infra.config_loader import ConfigLoader, ConfigNotConfiguredError
from src.infra.log_handler import LogHandler


class NoGamesConfiguredError(Exception):
    """ゲーム情報が1件も読み込めなかったことを示す例外."""


@dataclass
class MainWindowBootstrapResult:
    """MainWindow の初期化に必要な依存と初期データ."""

    games: List[GameEntry]
    browsers: Sequence[str]
    scanner: WindowScanner
    recorder: SessionRecorder
    state_tracker: GameStateTracker
    today_game_minutes: Dict[str, float]
    today_completed_seconds: float


@dataclass(frozen=True)
class BootstrapDependencies:
    """MainWindowBootstrapper が生成する依存クラス群."""

    config_loader_cls: type = ConfigLoader
    game_info_loader_cls: type = GameInfoLoader
    window_scanner_cls: type = WindowScanner
    log_handler_cls: type = LogHandler
    session_recorder_cls: type = SessionRecorder
    game_state_tracker_cls: type = GameStateTracker


class MainWindowBootstrapError(Exception):
    """MainWindow 初期化でユーザー向けに扱う例外."""

    def __init__(
        self,
        status_message: str,
        log_message: Optional[str] = None,
        *,
        open_settings: bool = False,
        open_game_catalog: bool = False,
        alert_title: Optional[str] = None,
        alert_message: Optional[str] = None,
    ) -> None:
        super().__init__(status_message)
        self.status_message = status_message
        self.log_message = log_message
        self.open_settings = open_settings
        self.open_game_catalog = open_game_catalog
        self.alert_title = alert_title
        self.alert_message = alert_message


class MainWindowBootstrapper:
    """MainWindow の依存構築・初期データ読み込みを担当."""

    def __init__(
        self,
        *,
        base_title: str,
        min_play_minutes: int,
        inactive_timeout_minutes: int,
        daily_stats: DailyStatsTracker,
        dependencies: Optional[BootstrapDependencies] = None,
        config_loader_cls: Optional[type] = None,
        game_info_loader_cls: Optional[type] = None,
        window_scanner_cls: Optional[type] = None,
        log_handler_cls: Optional[type] = None,
        session_recorder_cls: Optional[type] = None,
        game_state_tracker_cls: Optional[type] = None,
    ) -> None:
        self.base_title = base_title
        self.min_play_minutes = min_play_minutes
        self.inactive_timeout_minutes = inactive_timeout_minutes
        self.daily_stats = daily_stats
        self.dependencies = dependencies or BootstrapDependencies(
            config_loader_cls=config_loader_cls or ConfigLoader,
            game_info_loader_cls=game_info_loader_cls or GameInfoLoader,
            window_scanner_cls=window_scanner_cls or WindowScanner,
            log_handler_cls=log_handler_cls or LogHandler,
            session_recorder_cls=session_recorder_cls or SessionRecorder,
            game_state_tracker_cls=game_state_tracker_cls or GameStateTracker,
        )

    def bootstrap(self, *, window_title: str) -> MainWindowBootstrapResult:
        """設定・サービス・初期統計をまとめて構築する."""
        try:
            deps = self.dependencies
            config = deps.config_loader_cls().load()
            games = deps.game_info_loader_cls(config).load()
            if not games:
                raise NoGamesConfiguredError

            browsers = config.window_scan.browsers
            scanner = deps.window_scanner_cls(
                excluded_titles=(
                    list(config.window_scan.excluded_titles)
                    + [self.base_title, window_title]
                )
            )

            log_handler = deps.log_handler_cls(config.log_handler)
            recorder = deps.session_recorder_cls(
                log_handler=log_handler,
                min_play_minutes=self.min_play_minutes,
            )
            state_tracker = deps.game_state_tracker_cls(
                recorder=recorder,
                daily_stats=self.daily_stats,
                browsers=list(browsers),
                inactive_timeout_minutes=self.inactive_timeout_minutes,
            )
            today_game_minutes, today_completed_seconds = (
                recorder.log_handler.get_today_stats()
            )

            return MainWindowBootstrapResult(
                games=games,
                browsers=browsers,
                scanner=scanner,
                recorder=recorder,
                state_tracker=state_tracker,
                today_game_minutes=today_game_minutes,
                today_completed_seconds=today_completed_seconds,
            )
        except ConfigNotConfiguredError as e:
            raise MainWindowBootstrapError(
                "設定が未作成です。設定画面で入力して保存してください。",
                str(e),
                open_settings=True,
            ) from e
        except NoGamesConfiguredError as e:
            raise MainWindowBootstrapError(
                "ゲーム情報が未登録です。ゲーム管理で追加してください。",
                open_game_catalog=True,
            ) from e
        except FileNotFoundError as e:
            raise MainWindowBootstrapError(
                "認証情報ファイルが見つかりません。設定画面で認証JSONを確認してください。",
                f"認証情報ファイルが見つかりません: {e}",
                open_settings=True,
                alert_title="認証情報ファイルが見つかりません",
                alert_message=(
                    "設定されている認証JSONファイルを開けませんでした。\n"
                    "設定画面で認証JSONのパスを選び直してください。"
                ),
            ) from e
        except Exception as e:
            raise MainWindowBootstrapError(
                "ログハンドラー初期化エラー",
                f"ログハンドラーの初期化に失敗しました: {e}",
            ) from e

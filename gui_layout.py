"""Layout builder for Game Time Tracker GUI (PySide6)."""

from dataclasses import dataclass

from PySide6.QtWidgets import QLabel, QListWidget, QVBoxLayout, QWidget, QHBoxLayout, QTableWidget, QHeaderView

# ウィジェット高さ定数
ACTIVE_DISPLAY_HEIGHT = 30  # プレイ中ゲーム表示の高さ（1行分）
SESSION_TIME_DISPLAY_HEIGHT = 24  # セッション時間表示の高さ
TODAY_TIME_DISPLAY_HEIGHT = 32  # 今日のプレイ時間表示の高さ
WINDOW_LIST_MIN_HEIGHT = 200  # ウィンドウリストの最小高さ
TODAY_GAMES_TABLE_MIN_HEIGHT = 100  # 今日のゲーム一覧テーブルの最小高さ


@dataclass
class LayoutWidgets:
    """メインウィンドウのウィジェット参照を保持するデータクラス."""

    today_label: QLabel
    today_time_display: QLabel
    session_label: QLabel
    session_time_display: QLabel
    active_label: QLabel
    active_display: QLabel
    today_games_label: QLabel
    today_games_table: QTableWidget
    window_label: QLabel
    window_list: QListWidget
    active_min_height: int
    active_max_height: int
    today_games_min_height: int
    window_min_height: int


def build_main_layout(parent: QWidget) -> LayoutWidgets:
    """メインレイアウトを作成して親ウィンドウにアタッチする."""
    active_display = QLabel('---', parent)
    active_min_height = ACTIVE_DISPLAY_HEIGHT
    active_max_height = ACTIVE_DISPLAY_HEIGHT
    active_display.setMinimumHeight(active_min_height)  # 1行前提
    active_display.setMaximumHeight(active_max_height)  # 1行分で固定
    session_time_display = QLabel('---', parent)
    session_time_display.setFixedHeight(SESSION_TIME_DISPLAY_HEIGHT)
    today_time_display = QLabel('00:00:00', parent)
    today_time_display.setFixedHeight(TODAY_TIME_DISPLAY_HEIGHT)
    today_time_display.setStyleSheet("font-size: 20px; font-weight: bold;")
    window_list = QListWidget(parent)
    window_min_height = WINDOW_LIST_MIN_HEIGHT
    window_list.setMinimumHeight(window_min_height)

    main_layout = QVBoxLayout()

    today_label = QLabel('今日のプレイ時間:', parent)
    today_row = QHBoxLayout()
    today_row.addWidget(today_label)
    today_row.addWidget(today_time_display)
    today_row.addStretch()
    main_layout.addLayout(today_row)

    session_label = QLabel('現在のセッション時間:', parent)
    main_layout.addWidget(session_label)
    main_layout.addWidget(session_time_display)

    active_label = QLabel('プレイ中のゲーム:', parent)
    main_layout.addWidget(active_label)
    main_layout.addWidget(active_display)

    today_games_label = QLabel('今日プレイしたゲーム:', parent)
    main_layout.addWidget(today_games_label)
    today_games_table = QTableWidget(parent)
    today_games_table.setColumnCount(2)
    today_games_table.setHorizontalHeaderLabels(['ゲーム名', 'プレイ時間'])
    today_games_table.horizontalHeader().setStretchLastSection(False)
    today_games_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
    today_games_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
    today_games_table.verticalHeader().setVisible(False)
    today_games_min_height = TODAY_GAMES_TABLE_MIN_HEIGHT
    today_games_table.setMinimumHeight(today_games_min_height)
    main_layout.addWidget(today_games_table)

    window_label = QLabel('現在のウィンドウタイトル:', parent)
    main_layout.addWidget(window_label)
    main_layout.addWidget(window_list)

    parent.setLayout(main_layout)

    return LayoutWidgets(
        today_label=today_label,
        today_time_display=today_time_display,
        session_label=session_label,
        session_time_display=session_time_display,
        active_label=active_label,
        active_display=active_display,
        today_games_label=today_games_label,
        today_games_table=today_games_table,
        window_label=window_label,
        window_list=window_list,
        active_min_height=active_min_height,
        active_max_height=active_max_height,
        today_games_min_height=today_games_min_height,
        window_min_height=window_min_height,
    )

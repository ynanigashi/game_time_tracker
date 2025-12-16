"""Layout builder for Game Time Tracker GUI (PySide6)."""

from dataclasses import dataclass

from PySide6.QtWidgets import QLabel, QListWidget, QVBoxLayout, QWidget, QHBoxLayout


@dataclass
class LayoutWidgets:
    """Holds widget references for the main window."""

    today_label: QLabel
    today_time_display: QLabel
    session_label: QLabel
    session_time_display: QLabel
    active_label: QLabel
    active_display: QLabel
    window_label: QLabel
    window_list: QListWidget
    session_height: int
    active_min_height: int
    active_max_height: int
    window_min_height: int


def build_main_layout(parent: QWidget) -> LayoutWidgets:
    """Create and attach the main layout to the parent window."""
    active_display = QLabel('---', parent)
    active_min_height = 30
    active_max_height = 30
    active_display.setMinimumHeight(active_min_height)  # 1行前提
    active_display.setMaximumHeight(active_max_height)  # 1行分で固定
    session_time_display = QLabel('---', parent)
    session_height = 24
    session_time_display.setFixedHeight(session_height)
    today_time_display = QLabel('00:00:00', parent)
    today_time_display.setFixedHeight(32)
    today_time_display.setStyleSheet("font-size: 20px; font-weight: bold;")
    window_list = QListWidget(parent)
    window_min_height = 200  # ウィンドウタイトルは複数並ぶ想定
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
        window_label=window_label,
        window_list=window_list,
        session_height=session_height,
        active_min_height=active_min_height,
        active_max_height=active_max_height,
        window_min_height=window_min_height,
    )

from src.app.session_state import GameSessionState
from src.core.models import GameEntry


def test_update_scan_result_replaces_caches():
    state = GameSessionState()
    active = GameEntry(game_title="Active", window_title="Active")
    inactive = GameEntry(game_title="Inactive", window_title="Inactive")

    state.update_scan_result(
        active_games=[active],
        inactive_games=[inactive],
        window_titles=["Active Window", "Inactive Window"],
    )

    assert state.active_games_cache == [active]
    assert state.inactive_games_cache == [inactive]
    assert state.latest_window_titles == ["Active Window", "Inactive Window"]

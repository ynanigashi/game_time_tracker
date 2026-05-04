from src.ui.report_tab_state import ReportTabState


def test_mark_tab_clean_tracks_loaded_and_clears_dirty():
    state = ReportTabState(dirty_tabs={1})

    state.mark_tab_clean(1, trend_tab=1)

    assert state.loaded_tabs == {1}
    assert state.dirty_tabs == set()
    assert state.title_filter_dirty is False


def test_mark_all_dirty_and_reset_cache():
    state = ReportTabState(
        title_filter_dirty=False,
        last_summary=object(),
        title_filter_summary=object(),
        last_trend_series=[],
    )

    state.mark_all_dirty({0, 1, 2})
    state.reset_cached_report_data()

    assert state.dirty_tabs == {0, 1, 2}
    assert state.title_filter_dirty is True
    assert state.last_summary is None
    assert state.title_filter_summary is None
    assert state.last_trend_series is None

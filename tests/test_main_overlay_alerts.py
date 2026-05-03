# pyright: reportAttributeAccessIssue=false, reportArgumentType=false
# pyright: reportCallIssue=false, reportOptionalMemberAccess=false

from tests.helpers.main_test_imports import *  # noqa: F401,F403


class TestOverlayMethods(unittest.TestCase):
    """オーバーレイ更新/終了メソッドのテスト."""

    def _create_mock_main_window(self):
        return create_mock_main_window(include_state_tracker=False, include_ui=False)

    def test_refresh_overlay_time_updates_text(self):
        """_refresh_overlay_timeはtoday_time_displayの値をオーバーレイへ反映."""
        window = self._create_mock_main_window()
        window.overlay_window = MagicMock()
        window.w = MagicMock()
        window.w.today_time_display.text.return_value = "01:23:45.6"

        window._refresh_overlay_time()

        window.overlay_window.set_today_text.assert_called_once_with("01:23:45.6")

    def test_close_overlay_closes_and_clears_reference(self):
        """_close_overlayはcloseを呼び、参照をNoneにする."""
        window = self._create_mock_main_window()
        overlay = MagicMock()
        window.overlay_window = overlay

        window._close_overlay()

        overlay.close.assert_called_once()
        self.assertIsNone(window.overlay_window)

    def test_sync_overlay_visibility_shows_when_window_is_background(self):
        """_sync_overlay_visibilityは背面時にshowを呼ぶ."""
        window = self._create_mock_main_window()
        overlay = MagicMock()
        overlay.isVisible.return_value = False
        window.overlay_window = overlay
        controller = window._get_overlay_controller()
        controller._evaluate_overlay_visibility = MagicMock(
            return_value=(True, "covered")
        )

        window._sync_overlay_visibility()

        overlay.show.assert_called_once()
        overlay.hide.assert_not_called()

    def test_sync_overlay_visibility_hides_when_window_is_foreground(self):
        """_sync_overlay_visibilityは前面時にhideを呼ぶ."""
        window = self._create_mock_main_window()
        overlay = MagicMock()
        overlay.isVisible.return_value = False
        window.overlay_window = overlay
        controller = window._get_overlay_controller()
        controller._evaluate_overlay_visibility = MagicMock(
            return_value=(False, "not_covered")
        )

        window._sync_overlay_visibility()

        overlay.hide.assert_called_once()
        overlay.show.assert_not_called()

    def test_sync_overlay_visibility_keeps_visible_overlay_visible_before_check(
            self):
        """表示中オーバーレイは右ドラッグ判定のため隠さず維持する."""
        window = self._create_mock_main_window()
        overlay = MagicMock()
        overlay.isVisible.return_value = True
        window.overlay_window = overlay
        controller = window._get_overlay_controller()
        controller._evaluate_overlay_visibility = MagicMock(
            return_value=(True, "covered")
        )

        window._sync_overlay_visibility()

        overlay.hide.assert_not_called()
        overlay.show.assert_not_called()

    def test_sync_overlay_visibility_hides_overlay_before_visible_window_cover_check(
            self):
        """メイン表示中は被覆判定前にオーバーレイ自身を一旦隠す."""
        window = self._create_mock_main_window()
        window.isVisible = MagicMock(return_value=True)
        window._has_playing_games = MagicMock(return_value=True)
        overlay = MagicMock()
        overlay.isVisible.side_effect = [True, False]
        window.overlay_window = overlay

        def cover_state():
            self.assertTrue(overlay.hide.called)
            return False, "no_cover_detected"

        window._get_today_display_cover_state = MagicMock(side_effect=cover_state)

        window._sync_overlay_visibility()

        overlay.hide.assert_called()
        overlay.show.assert_not_called()

    def test_sync_overlay_geometry_uses_default_position_without_saved_position(self):
        """保存位置がない場合はメインウィンドウ部品へ追従しない."""
        window = self._create_mock_main_window()
        overlay = MagicMock()
        overlay.width.return_value = 240
        overlay.height.return_value = 40
        window.overlay_window = overlay
        window.w = MagicMock()

        window._sync_overlay_geometry()

        overlay.setGeometry.assert_called_once_with(24, 24, 240, 40)
        window.w.today_time_display.mapToGlobal.assert_not_called()

    def test_sync_overlay_geometry_uses_saved_overlay_position(self):
        """保存済みのタスクトレイ用オーバーレイ位置を使う."""
        window = self._create_mock_main_window()
        window.overlay_position = (111, 222)
        overlay = MagicMock()
        overlay.width.return_value = 240
        overlay.height.return_value = 40
        window.overlay_window = overlay

        window._sync_overlay_geometry()

        overlay.setGeometry.assert_called_once_with(111, 222, 240, 40)

    def test_sync_overlay_geometry_follows_today_time_display_when_window_visible(self):
        """ウィンドウ表示中のオーバーレイは今日のプレイ時間表示へ追従する."""
        window = self._create_mock_main_window()
        window.isVisible = MagicMock(return_value=True)
        overlay = MagicMock()
        window.overlay_window = overlay
        point = MagicMock()
        point.x.return_value = 111
        point.y.return_value = 222
        rect = MagicMock()
        rect.topLeft.return_value = object()
        target = MagicMock()
        target.rect.return_value = rect
        target.mapToGlobal.return_value = point
        target.width.return_value = 333
        target.height.return_value = 44
        window._get_today_time_display = MagicMock(return_value=target)

        window._sync_overlay_geometry()

        overlay.setGeometry.assert_called_once_with(111, 222, 333, 44)

    def test_sync_overlay_geometry_does_not_overwrite_saved_position(self):
        """Programmatic overlay follow should not rewrite the saved tray position."""
        window = self._create_mock_main_window()
        window.isVisible = MagicMock(return_value=True)
        window.overlay_position = (140, 250)
        controller = window._get_overlay_controller()
        overlay = main.TodayTimeOverlayWindow(on_moved=controller._on_overlay_moved)
        original_set_geometry = overlay.setGeometry

        def set_geometry_with_move_event(x, y, width, height):
            original_set_geometry(x, y, width, height)
            overlay.moveEvent(object())

        overlay.setGeometry = set_geometry_with_move_event
        window.overlay_window = overlay
        point = MagicMock()
        point.x.return_value = 111
        point.y.return_value = 222
        rect = MagicMock()
        rect.topLeft.return_value = object()
        target = MagicMock()
        target.rect.return_value = rect
        target.mapToGlobal.return_value = point
        target.width.return_value = 333
        target.height.return_value = 44
        window._get_today_time_display = MagicMock(return_value=target)

        window._sync_overlay_geometry()

        geometry = overlay.geometry()
        self.assertEqual(
            (geometry.x(), geometry.y(), geometry.width(), geometry.height()),
            (111, 222, 333, 44),
        )
        self.assertEqual(window.overlay_position, (140, 250))

    def test_sync_overlay_geometry_does_not_reset_while_dragging(self):
        """ドラッグ中はUI更新でオーバーレイ位置を戻さない."""
        window = self._create_mock_main_window()
        window.isVisible = MagicMock(return_value=True)
        overlay = MagicMock()
        overlay.is_dragging.return_value = True
        window.overlay_window = overlay
        window._get_today_time_display = MagicMock()

        window._sync_overlay_geometry()

        overlay.setGeometry.assert_not_called()
        window._get_today_time_display.assert_not_called()

    def test_overlay_drag_handle_hit_test_is_limited_to_left_edge(self):
        """オーバーレイ左端だけをドラッグハンドルとして扱う."""
        overlay = main.TodayTimeOverlayWindow()
        overlay.setGeometry(100, 200, 240, 40)

        self.assertTrue(overlay._is_drag_handle_global_point(100, 220))
        self.assertTrue(overlay._is_drag_handle_global_point(107, 220))
        self.assertFalse(overlay._is_drag_handle_global_point(108, 220))
        self.assertFalse(overlay._is_drag_handle_global_point(150, 220))

    def test_overlay_drag_handle_uses_grab_cursor(self):
        """ハンドル上は掴めることが分かるカーソルにする."""
        overlay = main.TodayTimeOverlayWindow()

        self.assertEqual(
            overlay._drag_handle.cursor,
            main.Qt.CursorShape.OpenHandCursor,
        )
        overlay._set_drag_cursor(active=True)
        self.assertEqual(
            overlay._drag_handle.cursor,
            main.Qt.CursorShape.ClosedHandCursor,
        )
        self.assertEqual(overlay.cursor, main.Qt.CursorShape.ClosedHandCursor)
        self.assertEqual(
            overlay._drag_handle_window.cursor,
            main.Qt.CursorShape.ClosedHandCursor,
        )

    def test_overlay_uses_separate_handle_window(self):
        """クリック透過オーバーレイとは別のハンドルウィンドウを表示する."""
        overlay = main.TodayTimeOverlayWindow()
        overlay.setGeometry(100, 200, 240, 40)

        overlay.show()

        handle_geometry = overlay._drag_handle_window.geometry()
        self.assertTrue(overlay._drag_handle_window.isVisible())
        self.assertEqual(
            (
                handle_geometry.x(),
                handle_geometry.y(),
                handle_geometry.width(),
                handle_geometry.height(),
            ),
            (100, 200, 8, 40),
        )

        overlay.hide()

        self.assertFalse(overlay._drag_handle_window.isVisible())

    def test_overlay_drag_handle_hit_test_uses_native_window_rect(self):
        """Win32の実ウィンドウ矩形でハンドル当たり判定を行う."""
        overlay = main.TodayTimeOverlayWindow()
        overlay.setGeometry(100, 200, 240, 40)

        with patch("src.app.controllers.overlay.sys.platform", "win32"), patch.object(
            overlay,
            "_native_window_rect",
            return_value=(150, 300, 510, 360),
        ):
            self.assertTrue(overlay._is_drag_handle_global_point(150, 320))
            self.assertTrue(overlay._is_drag_handle_global_point(161, 320))
            self.assertFalse(overlay._is_drag_handle_global_point(162, 320))

    def test_overlay_drag_handle_moves_overlay_with_mouse_drag(self):
        """左端ハンドルのドラッグでオーバーレイ自体を移動する."""
        moved_positions = []
        on_finished = MagicMock()
        on_dragged = MagicMock()
        overlay = main.TodayTimeOverlayWindow(
            on_moved=lambda x, y: moved_positions.append((x, y)),
            on_dragged=on_dragged,
            on_move_finished=on_finished,
        )
        overlay.setGeometry(100, 200, 240, 40)

        class FakeDragEvent:
            def __init__(self, x, y, *, button=None, buttons=None):
                self._point = MagicMock()
                self._point.x.return_value = x
                self._point.y.return_value = y
                self._button = button
                self._buttons = buttons
                self.accepted = False

            def globalPosition(self):
                return self._point

            def button(self):
                return self._button

            def buttons(self):
                return self._buttons

            def accept(self):
                self.accepted = True

        left_button = main.Qt.MouseButton.LeftButton
        press_event = FakeDragEvent(102, 210, button=left_button)
        move_event = FakeDragEvent(152, 260, buttons=left_button)
        release_event = FakeDragEvent(152, 260, button=left_button, buttons=0)

        self.assertTrue(overlay.start_handle_drag(press_event))
        self.assertTrue(overlay.move_handle_drag(move_event))
        on_dragged.assert_not_called()
        self.assertTrue(overlay.finish_handle_drag(release_event))

        geometry = overlay.geometry()
        self.assertEqual((geometry.x(), geometry.y()), (150, 250))
        self.assertEqual(moved_positions[-1], (150, 250))
        on_dragged.assert_called_once_with(150, 250)
        on_finished.assert_called_once()

    def test_overlay_drag_continues_from_global_cursor_when_mouse_move_is_missing(self):
        """mouseMoveが欠けてもUI tick側でグローバルカーソルから移動を継続する."""
        overlay = main.TodayTimeOverlayWindow()
        overlay.setGeometry(100, 200, 240, 40)
        overlay._start_drag_at_global_point(102, 210)

        point = MagicMock()
        point.x.return_value = 152
        point.y.return_value = 260
        with patch.object(overlay_components.QCursor, "pos", return_value=point), patch.object(
            overlay,
            "_is_left_mouse_button_pressed",
            return_value=True,
        ):
            result = overlay.continue_drag_from_global_cursor()

        geometry = overlay.geometry()
        self.assertTrue(result)
        self.assertEqual((geometry.x(), geometry.y()), (150, 250))

    def test_sync_overlay_skips_geometry_reset_while_global_drag_continues(self):
        """グローバルドラッグ継続中は追従ジオメトリで位置を戻さない."""
        window = self._create_mock_main_window()
        overlay = MagicMock()
        overlay.continue_drag_from_global_cursor.return_value = True
        overlay.isVisible.return_value = True
        window.overlay_window = overlay
        controller = window._get_overlay_controller()
        controller.refresh_overlay_time = MagicMock()
        controller.sync_overlay_geometry = MagicMock()
        controller.sync_overlay_visibility = MagicMock()

        window._sync_overlay()

        controller.refresh_overlay_time.assert_called_once()
        controller.sync_overlay_geometry.assert_not_called()
        controller.sync_overlay_visibility.assert_called_once()

    def test_overlay_native_drag_moves_overlay(self):
        """Qt子イベントが届かない場合もネイティブメッセージで移動する."""
        moved_positions = []
        on_finished = MagicMock()
        overlay = main.TodayTimeOverlayWindow(
            on_moved=lambda x, y: moved_positions.append((x, y)),
            on_move_finished=on_finished,
        )
        overlay.setGeometry(100, 200, 240, 40)

        with patch("src.app.controllers.overlay.sys.platform", "win32"), patch.object(
            main.TodayTimeOverlayWindow,
            "_capture_mouse",
        ), patch.object(
            main.TodayTimeOverlayWindow,
            "_release_mouse",
        ), patch.object(overlay_components.QCursor, "pos") as mock_pos:
            point = MagicMock()
            point.x.return_value = 102
            point.y.return_value = 210
            mock_pos.return_value = point
            overlay._handle_native_overlay_event(
                self._win_msg_address(overlay_components.WM_LBUTTONDOWN, 0)
            )

            point.x.return_value = 152
            point.y.return_value = 260
            overlay._handle_native_overlay_event(
                self._win_msg_address(
                    overlay_components.WM_MOUSEMOVE,
                    overlay_components.MK_LBUTTON,
                )
            )
            overlay._handle_native_overlay_event(
                self._win_msg_address(overlay_components.WM_LBUTTONUP, 0)
            )

        geometry = overlay.geometry()
        self.assertEqual((geometry.x(), geometry.y()), (150, 250))
        self.assertEqual(moved_positions[-1], (150, 250))
        on_finished.assert_called_once()

    _native_messages = []

    @classmethod
    def _win_msg_address(cls, message_id, wparam):
        msg = overlay_components._WinMsg()
        msg.message = message_id
        msg.wParam = wparam
        cls._native_messages.append(msg)
        return ctypes.addressof(msg)

    def test_overlay_move_callback_updates_overlay_position(self):
        """ドラッグ移動後の位置をタスクトレイ用オーバーレイ位置に反映する."""
        window = self._create_mock_main_window()
        controller = window._get_overlay_controller()

        controller._on_overlay_moved(140, 250)

        self.assertEqual(window.overlay_position, (140, 250))

    def test_overlay_drag_moves_visible_main_window_with_today_display(self):
        """ウィンドウ表示中のオーバーレイドラッグはメインウィンドウも動かす."""
        window = self._create_mock_main_window()
        window.isVisible = MagicMock(return_value=True)
        geometry = MagicMock()
        geometry.x.return_value = 10
        geometry.y.return_value = 20
        window.geometry = MagicMock(return_value=geometry)
        window.move = MagicMock()
        point = MagicMock()
        point.x.return_value = 100
        point.y.return_value = 200
        rect = MagicMock()
        rect.topLeft.return_value = object()
        target = MagicMock()
        target.rect.return_value = rect
        target.mapToGlobal.return_value = point
        window._get_today_time_display = MagicMock(return_value=target)
        controller = window._get_overlay_controller()

        controller._on_overlay_dragged(140, 250)

        window.move.assert_called_once_with(50, 70)

    def test_align_today_display_to_overlay_position_moves_main_window(self):
        """メイン表示時は今日のプレイ時間表示を保存済みオーバーレイ位置へ合わせる."""
        window = self._create_mock_main_window()
        window.overlay_position = (140, 250)
        geometry = MagicMock()
        geometry.x.return_value = 10
        geometry.y.return_value = 20
        window.geometry = MagicMock(return_value=geometry)
        window.move = MagicMock()
        point = MagicMock()
        point.x.return_value = 100
        point.y.return_value = 200
        rect = MagicMock()
        rect.topLeft.return_value = object()
        target = MagicMock()
        target.rect.return_value = rect
        target.mapToGlobal.return_value = point
        window._get_today_time_display = MagicMock(return_value=target)

        window._align_today_display_to_overlay_position()

        window.move.assert_called_once_with(50, 70)

    def test_show_main_window_from_tray_aligns_after_processing_events_twice(self):
        """トレイからの表示時はレイアウト確定後に位置合わせを再補正する."""
        window = self._create_mock_main_window()
        calls = []
        window.show = MagicMock(side_effect=lambda: calls.append("show"))
        window._process_pending_ui_events = MagicMock(
            side_effect=lambda: calls.append("process")
        )
        window._align_today_display_to_overlay_position = MagicMock(
            side_effect=lambda: calls.append("align")
        )
        window.raise_ = MagicMock(side_effect=lambda: calls.append("raise"))
        window.activateWindow = MagicMock(side_effect=lambda: calls.append("activate"))
        window._sync_tray_window_actions = MagicMock(
            side_effect=lambda: calls.append("tray")
        )
        window._sync_overlay = MagicMock(side_effect=lambda: calls.append("overlay"))

        window._show_main_window_from_tray()

        self.assertEqual(
            calls,
            ["show", "process", "align", "process", "align", "raise", "activate", "tray", "overlay"],
        )

    def test_should_show_overlay_returns_false_when_not_covered(self):
        """非アクティブでも重なっていなければオーバーレイは表示しない."""
        window = self._create_mock_main_window()
        window.tray_overlay_enabled = True
        window.isVisible = MagicMock(return_value=False)
        window.games = []

        result = window._should_show_overlay()

        self.assertFalse(result)

    def test_should_show_overlay_returns_true_when_covered(self):
        """非アクティブかつ重なっている場合のみ表示する."""
        window = self._create_mock_main_window()
        window.tray_overlay_enabled = True
        window.isVisible = MagicMock(return_value=False)
        game = models.GameEntry(game_title="TestGame", window_title="TestGame")
        game.is_playing = True
        window.games = [game]

        result = window._should_show_overlay()

        self.assertTrue(result)

    def test_should_show_overlay_returns_false_when_main_window_foreground(self):
        """ウィンドウ表示中かつ前面ならオーバーレイを隠す."""
        window = self._create_mock_main_window()
        window.tray_overlay_enabled = True
        window.isVisible = MagicMock(return_value=True)
        window._get_today_display_cover_state = MagicMock(
            return_value=(False, "foreground_not_foreign")
        )
        game = models.GameEntry(game_title="TestGame", window_title="TestGame")
        game.is_playing = True
        window.games = [game]

        result = window._should_show_overlay()

        self.assertFalse(result)

    def test_should_show_overlay_returns_true_when_visible_window_is_background(self):
        """ウィンドウ表示中でも他ウィンドウが前面ならオーバーレイを表示する."""
        window = self._create_mock_main_window()
        window.tray_overlay_enabled = True
        window.isVisible = MagicMock(return_value=True)
        window._get_today_display_cover_state = MagicMock(
            return_value=(True, "covered_native_points")
        )
        game = models.GameEntry(game_title="TestGame", window_title="TestGame")
        game.is_playing = True
        window.games = [game]

        result = window._should_show_overlay()

        self.assertTrue(result)

    def test_visible_window_overlay_ignores_tray_overlay_menu_setting(self):
        """ウィンドウ表示中の被覆オーバーレイはトレイ用設定に依存しない."""
        window = self._create_mock_main_window()
        window.tray_overlay_enabled = False
        window.isVisible = MagicMock(return_value=True)
        window._get_today_display_cover_state = MagicMock(
            return_value=(True, "covered_native_points")
        )
        game = models.GameEntry(game_title="TestGame", window_title="TestGame")
        game.is_playing = True
        window.games = [game]

        result = window._should_show_overlay()

        self.assertTrue(result)

    def test_should_show_overlay_ignores_overtime_alert_disabled(self):
        """時間超過防止アラートOFF時はオーバーレイを表示しない."""
        window = self._create_mock_main_window()
        window.tray_overlay_enabled = True
        window.overtime_alert_enabled = False
        window.isVisible = MagicMock(return_value=False)
        game = models.GameEntry(game_title="TestGame", window_title="TestGame")
        game.is_playing = True
        window.games = [game]

        result = window._should_show_overlay()

        self.assertTrue(result)

    def test_covered_by_foreign_window_returns_true(self):
        """5点のうち閾値以上が他ウィンドウで覆われればTrue."""
        window = self._create_mock_main_window()
        target = MagicMock()
        window._get_today_time_display = MagicMock(return_value=target)

        window._global_rect_of_widget = MagicMock(return_value=(100, 200, 220, 230))
        window._foreground_rect_if_foreign = MagicMock(
            return_value=(0, 0, 2000, 2000)
        )
        window._root_window = MagicMock(return_value=123)
        window._to_native_point = MagicMock(side_effect=lambda x, y: (x, y))
        window._find_covering_foreign_window_at_point = MagicMock(
            side_effect=[0, 999, 999, 0, 0])

        with patch('src.app.main.get_foreground_hwnd', return_value=123):
            self.assertTrue(window._is_today_display_covered_by_foreground_window())

    def test_covered_by_non_foreground_foreign_window_returns_true(self):
        """前面ウィンドウ以外がtoday表示部を覆っていても検出する."""
        window = self._create_mock_main_window()
        target = MagicMock()
        window._get_today_time_display = MagicMock(return_value=target)

        window._global_rect_of_widget = MagicMock(return_value=(100, 200, 220, 230))
        window._foreground_rect_if_foreign = MagicMock(
            side_effect=AssertionError("foreground rect should not be required")
        )
        window._to_native_point = MagicMock(side_effect=lambda x, y: (x, y))
        window._find_covering_foreign_window_at_point = MagicMock(
            side_effect=[999, 999, 0, 0, 0]
        )

        self.assertTrue(window._is_today_display_covered_by_foreground_window())

    def test_uncovered_when_top_window_is_own_returns_false(self):
        """5点すべて未被覆ならFalse."""
        window = self._create_mock_main_window()
        window.w = MagicMock()
        target = MagicMock()
        point = MagicMock()
        point.x.return_value = 150
        point.y.return_value = 250
        target.rect.return_value.topLeft.return_value = object()
        target.mapToGlobal.return_value = point
        target.width.return_value = 140
        target.height.return_value = 40
        window.w.today_time_display = target
        window._is_own_window = MagicMock(return_value=False)
        window._window_rect = MagicMock(return_value=(0, 0, 2000, 2000))
        window._to_native_point = MagicMock(side_effect=lambda x, y: (x, y))
        window._find_covering_foreign_window_at_point = MagicMock(side_effect=[
            0, 0, 0, 0, 0,
            0, 0, 0, 0, 0,
        ])

        with patch('src.app.win32_helpers.get_foreground_hwnd', return_value=123):
            self.assertFalse(window._is_today_display_covered_by_foreground_window())

    def test_sample_points_from_rect_uses_25_75_offsets(self):
        """_sample_points_from_rectは中心+25/75%点を返す."""
        rect = (100, 200, 200, 300)  # width=100, height=100

        points = main.MainWindow._sample_points_from_rect(rect)

        self.assertEqual(points, [(150, 250), (125, 225),
                         (175, 225), (125, 275), (175, 275)])

    def test_to_native_point_uses_window_rect_offset(self):
        """ネイティブ座標変換は画面原点ではなくウィンドウ矩形基準で行う."""
        window = self._create_mock_main_window()
        frame_geometry = MagicMock()
        frame_geometry.x.return_value = 1000
        frame_geometry.y.return_value = 500
        frame_geometry.width.return_value = 800
        frame_geometry.height.return_value = 600
        window.frameGeometry = MagicMock(return_value=frame_geometry)

        with patch("src.app.main.window_handle_of", return_value=123), patch(
            "src.app.main.window_rect",
            return_value=(2000, 1000, 3600, 2200),
        ):
            point = window._to_native_point(1100, 650)

        self.assertEqual(point, (2200, 1300))

    def test_find_covering_foreign_window_at_point_returns_covering_hwnd(self):
        """_find_covering_foreign_window_at_pointは点を覆う他ウィンドウを返す."""
        window = self._create_mock_main_window()
        window._window_at_point = MagicMock(return_value=500)
        window._is_own_window = MagicMock(return_value=False)
        window._window_rect = MagicMock(return_value=(0, 0, 1000, 1000))
        window._window_handle_of = MagicMock(return_value=0)
        window._window_below = MagicMock(return_value=0)

        result = window._find_covering_foreign_window_at_point(100, 200)

        self.assertEqual(result, 500)

    def test_find_covering_foreign_window_at_point_does_not_walk_below_top_window(self):
        """最前面候補が覆っていなければ背面ウィンドウを被覆として拾わない."""
        window = self._create_mock_main_window()
        window._window_at_point = MagicMock(return_value=500)
        window._is_own_window = MagicMock(return_value=False)
        window._window_rect = MagicMock(return_value=(0, 0, 10, 10))
        window._window_below = MagicMock(return_value=600)

        result = window._find_covering_foreign_window_at_point(100, 200)

        self.assertEqual(result, 0)
        window._window_below.assert_not_called()

    def test_find_covering_foreign_window_at_point_accepts_expected_root(self):
        """expected_root_hwnd が一致する最前面ウィンドウは被覆として扱う."""
        window = self._create_mock_main_window()
        window._window_at_point = MagicMock(return_value=501)
        window._is_own_window = MagicMock(return_value=False)
        window._window_rect = MagicMock(return_value=(0, 0, 1000, 1000))
        window._root_window = MagicMock(side_effect=lambda hwnd: 500 if hwnd == 501 else hwnd)

        result = window._find_covering_foreign_window_at_point(
            100,
            200,
            expected_root_hwnd=500,
        )

        self.assertEqual(result, 501)

    def test_find_covering_foreign_window_at_point_rejects_unexpected_root(self):
        """expected_root_hwnd が違う最前面ウィンドウは被覆として扱わない."""
        window = self._create_mock_main_window()
        window._window_at_point = MagicMock(return_value=501)
        window._is_own_window = MagicMock(return_value=False)
        window._window_rect = MagicMock(return_value=(0, 0, 1000, 1000))
        window._root_window = MagicMock(side_effect=lambda hwnd: 500 if hwnd == 501 else hwnd)

        result = window._find_covering_foreign_window_at_point(
            100,
            200,
            expected_root_hwnd=999,
        )

        self.assertEqual(result, 0)

    def test_find_covering_foreign_window_at_point_ignores_non_covering_hwnd(self):
        """矩形が点を含まない候補ウィンドウは被りとして扱わない."""
        window = self._create_mock_main_window()
        window._window_at_point = MagicMock(return_value=500)
        window._is_own_window = MagicMock(return_value=False)
        window._window_rect = MagicMock(return_value=(0, 0, 10, 10))
        window._window_below = MagicMock(return_value=0)

        result = window._find_covering_foreign_window_at_point(100, 200)

        self.assertEqual(result, 0)

    def test_find_covering_foreign_window_at_point_returns_zero_for_own_window(self):
        """判定点が自ウィンドウなら被覆なしとして0を返す."""
        window = self._create_mock_main_window()
        window._window_at_point = MagicMock(return_value=111)
        window._is_own_window = MagicMock(return_value=True)
        window._window_below = MagicMock(return_value=222)
        window._window_rect = MagicMock(return_value=(0, 0, 1000, 1000))

        result = window._find_covering_foreign_window_at_point(100, 200)

        self.assertEqual(result, 0)
        window._window_below.assert_not_called()

class TestOvertimeAlertMethods(unittest.TestCase):
    """時間超過防止アラートのテスト."""

    def _create_mock_main_window(self):
        return create_mock_main_window(include_state_tracker=False, include_ui=False)

    def test_update_overtime_alert_beeps_once_on_threshold_cross(self):
        """閾値を跨いだときのみ1回通知する."""
        window = self._create_mock_main_window()
        window.overtime_alert_enabled = True
        tracker = main.OvertimeAlertTracker(
            thresholds_minutes=main.OVERTIME_ALERT_THRESHOLDS_MINUTES,
            alerted_threshold_minutes=set(),
            last_checked_seconds=44 * 60,
            initialized=True,
        )
        window._overtime_alert_tracker = tracker

        with patch.object(main.QApplication, "beep") as mock_beep:
            window._update_overtime_alert((45 * 60) + 1)
            window._update_overtime_alert((46 * 60))

        self.assertEqual(mock_beep.call_count, 1)
        self.assertIn(45, tracker.alerted_threshold_minutes)

    def test_update_overtime_alert_does_not_beep_when_disabled(self):
        """トグルOFF時は閾値を跨いでも通知しない."""
        window = self._create_mock_main_window()
        window.overtime_alert_enabled = False
        tracker = main.OvertimeAlertTracker(
            thresholds_minutes=main.OVERTIME_ALERT_THRESHOLDS_MINUTES,
            alerted_threshold_minutes=set(),
            last_checked_seconds=44 * 60,
            initialized=True,
        )
        window._overtime_alert_tracker = tracker

        with patch.object(main.QApplication, "beep") as mock_beep:
            window._update_overtime_alert((45 * 60) + 1)

        mock_beep.assert_not_called()
        self.assertNotIn(45, tracker.alerted_threshold_minutes)

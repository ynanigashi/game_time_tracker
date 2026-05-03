import unittest
from types import SimpleNamespace

from tests.test_stubs import FakeSignal, install_stubs

install_stubs()

from src.app.controllers.window_title import MainWindowTitleController
from src.app.window_title_state import WindowTitleState


class MainWindowTitleControllerTest(unittest.TestCase):
    def test_initialize_copy_updates_injected_state(self):
        window_list = SimpleNamespace(
            itemClicked=FakeSignal(),
            setToolTip=lambda _text: None,
        )
        state = WindowTitleState()
        owner = SimpleNamespace(
            w=SimpleNamespace(window_list=window_list),
            _get_window_list_widget=lambda: window_list,
            _on_window_title_item_clicked=lambda _item: None,
            _initialize_window_title_context_menu=lambda _list: None,
        )
        controller = MainWindowTitleController(
            owner,
            qmenu_cls=object,
            state=state,
        )

        controller.initialize_window_title_copy()

        self.assertTrue(state.copy_connected)


if __name__ == "__main__":
    unittest.main()

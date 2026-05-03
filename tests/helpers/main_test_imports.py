# pyright: reportAttributeAccessIssue=false, reportArgumentType=false
# pyright: reportCallIssue=false, reportOptionalMemberAccess=false

from tests.test_stubs import fake_gspread, FakeLogHandler

import configparser
import ctypes
import logging
import os
import sys
import tempfile
import unittest
from datetime import datetime, time, timedelta
from logging.handlers import RotatingFileHandler
from pathlib import Path
from unittest.mock import MagicMock, PropertyMock, call, patch

import pygetwindow

from src.app import main
from src.app.controllers import overlay as overlay_components
from src.app.controllers import MainWindowBootstrapError
from src.core import adapters as services
from src.core import domain, models, time_utils, window_state
from src.core.text_utils import normalize_title
from tests.helpers.main_window_factory import (
    attach_window_title_stubs,
    create_mock_main_window,
)


# servicesモジュールにpygetwindowのスタブを設定
services.gw = pygetwindow

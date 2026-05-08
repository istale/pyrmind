"""Pyrmind - Python process manager for Procfile-based applications.

A Python clone of Overmind, using tmux for process isolation and output capture.
"""
__version__ = "0.2.0"
__author__ = "Pyrmind contributors"

from .procfile import ProcfileEntry, parse_procfile, read_procfile, parse_formation, expand_procfile
from .tmux_client import TmuxClient, TmuxProcessManager, TmuxOutput
from .socket_server import SocketServer, SocketClient
from .process_manager import ProcessManager, DaemonProcessManager, ProcessInfo
from .env import make_env, port_for_process

__all__ = [
    'ProcfileEntry',
    'parse_procfile',
    'read_procfile',
    'parse_formation',
    'expand_procfile',
    'TmuxClient',
    'TmuxProcessManager',
    'TmuxOutput',
    'SocketServer',
    'SocketClient',
    'ProcessManager',
    'DaemonProcessManager',
    'ProcessInfo',
    'make_env',
    'port_for_process',
]

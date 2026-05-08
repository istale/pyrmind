"""Attach mode - Aggregated log viewer for Pyrmind.

Uses curses to display output from all processes in a terminal UI,
similar to Overmind's connect command.
"""
import curses
import threading
import time
import sys
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass

from .socket_server import SocketClient


# ANSI color codes for process name prefixes
PROCESS_COLORS = [
    curses.COLOR_CYAN,    # web
    curses.COLOR_GREEN,   # worker
    curses.COLOR_YELLOW,  # assets
    curses.COLOR_MAGENTA, # api
    curses.COLOR_BLUE,    # db
    curses.COLOR_RED,     # error/crash
    curses.COLOR_WHITE,   # default
]

# Maximum lines to keep per process buffer
MAX_BUFFER_LINES = 1000


@dataclass
class ProcessBuffer:
    """Buffer for a single process's output."""
    name: str
    color_pair: int
    lines: List[str]
    last_len: int = 0


class LogAggregator:
    """Collects output from all processes via socket."""
    
    def __init__(self, socket_path: str):
        self.socket_path = socket_path
        self.client = SocketClient(socket_path)
        self.buffers: Dict[str, ProcessBuffer] = {}
        self.process_names: List[str] = []
        self.running = False
        self._lock = threading.Lock()
    
    def connect(self) -> bool:
        """Test connection to daemon."""
        result = self.client.status()
        return result.get('status') == 'ok'
    
    def refresh(self) -> Dict[str, ProcessBuffer]:
        """Poll output from all processes and update buffers."""
        # Get current status to see what processes exist
        result = self.client.status()
        
        if result.get('status') != 'ok':
            return self.buffers
        
        info = result.get('info', {})
        current_processes = list(info.keys())
        
        # Initialize buffers for new processes
        with self._lock:
            for i, name in enumerate(sorted(current_processes)):
                if name not in self.buffers:
                    color_idx = i % len(PROCESS_COLORS)
                    self.buffers[name] = ProcessBuffer(
                        name=name,
                        color_pair=color_idx + 1,  # color pairs start at 1
                        lines=[]
                    )
            self.process_names = sorted(current_processes)
        
        # Get output for each process
        for name in self.process_names:
            output = self.client.send_command('output', process=name)
            if output.get('status') == 'ok':
                new_lines = output.get('lines', [])
                with self._lock:
                    if name in self.buffers:
                        buffer = self.buffers[name]
                        # Only add new lines
                        if len(new_lines) > buffer.last_len:
                            buffer.lines.extend(new_lines[buffer.last_len:])
                            buffer.last_len = len(new_lines)
                            # Trim buffer if too long
                            if len(buffer.lines) > MAX_BUFFER_LINES:
                                buffer.lines = buffer.lines[-MAX_BUFFER_LINES:]
                                buffer.last_len = len(buffer.lines)
        
        return self.buffers


class AttachUI:
    """Curses-based UI for displaying aggregated logs."""
    
    def __init__(self, aggregator: LogAggregator, poll_interval: float = 0.5):
        self.aggregator = aggregator
        self.poll_interval = poll_interval
        self.scroll_offset: Dict[str, int] = {}  # per-process scroll position
        self.selected_idx = 0
        self.running = False
        self._selected_line_idx = 0  # Track which line is selected for scrolling
    
    def run(self, stdscr):
        """Main curses loop."""
        curses.curs_set(0)  # Hide cursor
        stdscr.nodelay(True)  # Non-blocking input
        
        # Initialize color pairs
        for i in range(len(PROCESS_COLORS)):
            curses.init_pair(i + 1, PROCESS_COLORS[i], curses.COLOR_BLACK)
        
        # Default color for when no processes
        curses.init_pair(len(PROCESS_COLORS) + 1, curses.COLOR_WHITE, curses.COLOR_BLACK)
        
        self.running = True
        last_refresh = 0
        
        while self.running:
            # Handle input
            self._handle_input(stdscr)
            
            # Refresh output periodically
            now = time.time()
            if now - last_refresh >= self.poll_interval:
                self.aggregator.refresh()
                last_refresh = now
            
            # Draw
            self._draw(stdscr)
            
            # Small delay to prevent CPU hogging
            curses.napms(50)
        
        # Clean up
        curses.curs_set(1)
    
    def _handle_input(self, stdscr):
        """Handle keyboard input."""
        try:
            key = stdscr.getch()
        except curses.error:
            return
        
        if key == -1:
            return
        
        # Quit on q or ESC
        if key in (ord('q'), ord('Q'), 27):
            self.running = False
            return
        
        # Arrow keys or vim-style navigation
        with self.aggregator._lock:
            process_names = list(self.aggregator.buffers.keys())
        
        if not process_names:
            return
        
        selected_name = process_names[self.selected_idx] if process_names else None
        
        # Scroll within selected process buffer
        if key in (curses.KEY_UP, ord('k')):
            if selected_name:
                with self.aggregator._lock:
                    if selected_name in self.aggregator.buffers:
                        buffer = self.aggregator.buffers[selected_name]
                        max_offset = max(0, len(buffer.lines) - 1)
                        self.scroll_offset[selected_name] = max(0, 
                            self.scroll_offset.get(selected_name, 0) - 1)
        
        elif key in (curses.KEY_DOWN, ord('j')):
            if selected_name:
                with self.aggregator._lock:
                    if selected_name in self.aggregator.buffers:
                        buffer = self.aggregator.buffers[selected_name]
                        max_offset = max(0, len(buffer.lines) - 1)
                        self.scroll_offset[selected_name] = min(max_offset,
                            self.scroll_offset.get(selected_name, 0) + 1)
        
        # Page up/down
        elif key == curses.KEY_PPAGE:  # Page Up
            if selected_name:
                with self.aggregator._lock:
                    if selected_name in self.aggregator.buffers:
                        self.scroll_offset[selected_name] = max(0,
                            self.scroll_offset.get(selected_name, 0) - 20)
        
        elif key == curses.KEY_NPAGE:  # Page Down
            if selected_name:
                with self.aggregator._lock:
                    if selected_name in self.aggregator.buffers:
                        buffer = self.aggregator.buffers[selected_name]
                        max_offset = max(0, len(buffer.lines) - 1)
                        self.scroll_offset[selected_name] = min(max_offset,
                            self.scroll_offset.get(selected_name, 0) + 20)
        
        # Home/End - scroll to beginning/end of selected buffer
        elif key == curses.KEY_HOME:
            if selected_name:
                self.scroll_offset[selected_name] = 0
        
        elif key == curses.KEY_END:
            if selected_name:
                with self.aggregator._lock:
                    if selected_name in self.aggregator.buffers:
                        buffer = self.aggregator.buffers[selected_name]
                        self.scroll_offset[selected_name] = max(0, len(buffer.lines) - 1)
        
        # Tab or Right/Left to switch between processes
        elif key in (curses.KEY_BTAB, curses.KEY_LEFT, ord('h')):
            if process_names:
                self.selected_idx = (self.selected_idx - 1) % len(process_names)
        
        elif key in (curses.KEY_RIGHT, ord('l'), 9):  # 9 = Tab
            if process_names:
                self.selected_idx = (self.selected_idx + 1) % len(process_names)
        
        # r to force refresh
        elif key in (ord('r'), ord('R')):
            self.aggregator.refresh()
    
    def _draw(self, stdscr):
        """Draw the UI."""
        height, width = stdscr.getmaxyx()
        
        # Clear screen
        stdscr.clear()
        
        # Header
        header = " Pyrmind Logs (q=quit, j/k=scroll, h/l=switch process, r=refresh) "
        stdscr.addstr(0, 0, header.ljust(width - 1), curses.A_REVERSE | curses.color_pair(8))
        
        # Status line
        with self.aggregator._lock:
            process_names = list(self.aggregator.buffers.keys())
            num_processes = len(process_names)
            num_lines_total = sum(len(b.lines) for b in self.aggregator.buffers.values())
        
        status = f" Processes: {num_processes} | Lines: {num_lines_total} | Time: {time.strftime('%H:%M:%S')}"
        stdscr.addstr(1, 0, status.ljust(width - 1), curses.A_DIM)
        
        # Process tabs (second line)
        if process_names:
            tab_y = 2
            tab_x = 0
            for i, name in enumerate(process_names):
                is_selected = (i == self.selected_idx)
                buffer = self.aggregator.buffers[name]
                attr = curses.A_REVERSE if is_selected else curses.A_DIM
                color = curses.color_pair(buffer.color_pair)
                
                tab_text = f" {name} [{len(buffer.lines)}] "
                if tab_x + len(tab_text) < width:
                    stdscr.addstr(tab_y, tab_x, tab_text, attr | color)
                    tab_x += len(tab_text)
        else:
            stdscr.addstr(2, 0, " No processes running ", curses.A_DIM)
        
        # Separator line
        stdscr.addstr(3, 0, "─" * (width - 1), curses.A_DIM)
        
        # Log content area
        content_start_y = 4
        content_height = height - content_start_y - 1
        
        if not process_names:
            stdscr.addstr(content_start_y, 0, " Waiting for process output... ", curses.A_DIM)
            if self.aggregator.connect():
                stdscr.addstr(content_start_y + 1, 0, " (Connected to daemon)", curses.A_DIM)
            else:
                stdscr.addstr(content_start_y + 1, 0, " (Cannot connect to daemon)", curses.color_pair(6))
            return
        
        # Draw logs for selected process (or all if few)
        with self.aggregator._lock:
            if 0 <= self.selected_idx < len(process_names):
                selected_name = process_names[self.selected_idx]
                if selected_name in self.aggregator.buffers:
                    buffer = self.aggregator.buffers[selected_name]
                    offset = self.scroll_offset.get(selected_name, 0)
                    
                    visible_lines = buffer.lines[offset:offset + content_height]
                    
                    for y, line in enumerate(visible_lines):
                        if y >= content_height:
                            break
                        
                        # Truncate line if needed
                        display_line = line[:width - 1]
                        try:
                            stdscr.addstr(content_start_y + y, 0, display_line)
                        except curses.error:
                            pass  # Ignore if can't write (e.g., at edge)
        
        # Footer with help
        footer = " ↑↓/j k: scroll | ←→/h l: switch | PgUp/PgDn: page | Home/End: start/end | q: quit "
        try:
            stdscr.addstr(height - 1, 0, footer.ljust(width - 1), curses.A_REVERSE)
        except curses.error:
            pass
        
        # Refresh display
        stdscr.refresh()


def start_attach(socket_path: str, poll_interval: float = 0.5):
    """Start attach mode with curses UI."""
    aggregator = LogAggregator(socket_path)
    
    if not aggregator.connect():
        print(f"Error: Cannot connect to daemon at {socket_path}")
        print("Is the daemon running?")
        sys.exit(1)
    
    ui = AttachUI(aggregator, poll_interval)
    
    try:
        curses.wrapper(ui.run)
    except KeyboardInterrupt:
        pass
    finally:
        print("\nDetached from Pyrmind.")


def start_attach_tmux(socket_path: str, session_name: str = "pyrmind-attach"):
    """Start attach mode in a new tmux window (alternative approach).
    
    This creates a tmux window that shows logs from all processes.
    """
    import subprocess
    
    # Check if tmux is available
    result = subprocess.run(['which', 'tmux'], capture_output=True)
    if result.returncode != 0:
        print("Error: tmux not found")
        sys.exit(1)
    
    # Create a new tmux window for the attach session
    # We'll run a Python script in that window that does the log aggregation
    
    cmd = f'python3 -c "from pyrmind.attach import start_attach; start_attach(\\\"{socket_path}\\\")"'
    
    # Create window and run attach
    subprocess.run([
        'tmux', 'new-window', '-n', session_name, cmd
    ])

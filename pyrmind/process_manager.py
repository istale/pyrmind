"""Process management for Pyrmind."""
import os
import signal
import subprocess
import time
from typing import Dict, Optional, List, Any
from dataclasses import dataclass
from threading import Thread, Event


@dataclass
class ProcessInfo:
    """Information about a managed process."""
    name: str
    command: str
    cwd: Optional[str]
    env: Dict[str, str]
    running: bool
    pid: Optional[int]
    tmux_pane: Optional[str]
    can_die: bool
    # Auto-restart tracking
    restart_count: int = 0
    last_restart_time: float = 0.0
    last_start_time: float = 0.0


class ProcessManager:
    """
    Manages processes from a Procfile.
    
    Uses tmux for process isolation and output capture.
    
    Args:
        session_name: Base name for the tmux session
        base_port: Starting port for PORT environment variable
        port_increment: How much to increment port per process
        auto_restart: If True, restart crashed processes automatically
        restart_cooldown: Seconds to wait before restarting a crashed process
        max_restart_count: Max restarts per process before giving up (0 = infinite)
    """
    
    def __init__(
        self,
        session_name: str = "pyrmind",
        base_port: int = 5000,
        port_increment: int = 10,
        auto_restart: bool = False,
        restart_cooldown: float = 5.0,
        max_restart_count: int = 3
    ):
        self.session_name = session_name
        self.base_port = base_port
        self.port_increment = port_increment
        self.auto_restart = auto_restart
        self.restart_cooldown = restart_cooldown
        self.max_restart_count = max_restart_count
        
        self.processes: Dict[str, ProcessInfo] = {}
        self._port_counter = 0
        
        # Lazy import to avoid circular dependency
        from .tmux_client import TmuxProcessManager
        self.tmux = TmuxProcessManager(session_name=session_name)
        
        # Watchdog thread for auto-restart
        self._watchdog_thread: Optional[Thread] = None
        self._watchdog_stop = Event()
    
    def load_procfile(self, path: str, formation: Optional[str] = None):
        """Load processes from a Procfile."""
        from .procfile import read_procfile, parse_formation, expand_procfile
        from .env import make_env
        
        entries = read_procfile(path)
        
        formation_dict = parse_formation(formation) if formation else {}
        expanded = expand_procfile(entries, formation_dict)
        
        # Assign ports and create process info
        for entry in expanded:
            port = self.base_port + self._port_counter
            self._port_counter += 1
            
            env = make_env(base_port=port)
            
            info = ProcessInfo(
                name=entry.name,
                command=entry.command,
                cwd=None,
                env=env,
                running=False,
                pid=None,
                tmux_pane=None,
                can_die=entry.can_die
            )
            self.processes[entry.name] = info
    
    def start(self):
        """Start all processes."""
        for name, info in self.processes.items():
            self._start_process(name, info)
        
        # Start watchdog if auto_restart is enabled
        if self.auto_restart:
            self._start_watchdog()
    
    def _start_process(self, name: str, info: ProcessInfo):
        """Start a single process."""
        env = dict(info.env)
        
        self.tmux.spawn(
            name=name,
            command=info.command,
            cwd=info.cwd,
            env=env
        )
        
        info.running = True
        info.last_start_time = time.time()
    
    def _start_watchdog(self):
        """Start the watchdog thread for auto-restart."""
        if self._watchdog_thread is not None and self._watchdog_thread.is_alive():
            return  # Already running
        
        self._watchdog_stop.clear()
        self._watchdog_thread = Thread(target=self._watchdog_loop, daemon=True)
        self._watchdog_thread.start()
    
    def _stop_watchdog(self):
        """Stop the watchdog thread."""
        self._watchdog_stop.set()
        if self._watchdog_thread is not None:
            self._watchdog_thread.join(timeout=2)
            self._watchdog_thread = None
    
    def _watchdog_loop(self):
        """Watchdog loop that checks for crashed processes and restarts them."""
        while not self._watchdog_stop.is_set():
            self._watchdog_stop.wait(timeout=1.0)  # Check every second
            
            if self._watchdog_stop.is_set():
                break
            
            self._check_and_restart_crashed()
    
    def _check_and_restart_crashed(self):
        """Check for crashed processes and restart if needed."""
        if not self.auto_restart:
            return
        
        tmux_status = self.tmux.get_status()
        
        for name, info in self.processes.items():
            if info.can_die:
                continue  # can_die processes are not restarted
            
            tmux_info = tmux_status.get(name, {})
            is_running = tmux_info.get('running', False)
            
            if is_running:
                continue  # Process is still running
            
            # Process has exited
            now = time.time()
            time_since_start = now - info.last_start_time
            
            # Check cooldown - don't restart if crashed too soon after starting
            if time_since_start < self.restart_cooldown:
                # Crashed immediately - increment restart count
                info.restart_count += 1
                
                # Check if we've exceeded max restarts
                if self.max_restart_count > 0 and info.restart_count > self.max_restart_count:
                    # Too many restarts, give up on this process
                    continue
            else:
                # Process was running for a while before crashing - reset count
                info.restart_count = 0
            
            # Check if we should restart
            if self.max_restart_count > 0 and info.restart_count > self.max_restart_count:
                # Already tried too many times
                continue
            
            # Check cooldown since last restart attempt
            if now - info.last_restart_time < self.restart_cooldown:
                continue
            
            # Restart the process
            print(f"[pyrmind] Process '{name}' crashed, restarting (attempt {info.restart_count + 1})...")
            info.last_restart_time = now
            self._start_process(name, info)
    
    def restart(self, name: str) -> bool:
        """Restart a specific process."""
        if name not in self.processes:
            return False
        
        info = self.processes[name]
        
        # Stop existing
        if info.running:
            self._stop_process(name)
        
        # Reset restart tracking on manual restart
        info.restart_count = 0
        
        # Start again
        self._start_process(name, info)
        return True
    
    def stop(self, name: str) -> bool:
        """Stop a specific process."""
        if name not in self.processes:
            return False
        return self._stop_process(name)
    
    def _stop_process(self, name: str):
        """Internal stop."""
        info = self.processes[name]
        if info.running:
            self.tmux.stop_process(name)
            info.running = False
    
    def kill_all(self):
        """Kill all processes and tmux session."""
        self._stop_watchdog()
        self.tmux.kill_all()
        for info in self.processes.values():
            info.running = False
    
    def get_status(self) -> Dict[str, Any]:
        """Get status of all processes."""
        tmux_status = self.tmux.get_status()
        
        status = {}
        for name, info in self.processes.items():
            tmux_info = tmux_status.get(name, {})
            
            status[name] = {
                'running': info.running,
                'command': info.command,
                'can_die': info.can_die,
                'tmux_pane': tmux_info.get('pane'),
                'pid': info.pid,
                'restart_count': info.restart_count,
                'auto_restart': self.auto_restart
            }
        
        return status
    
    def get_output(self) -> Dict[str, List[str]]:
        """Get recent output from all processes."""
        outputs = {}
        for name, client in self.tmux.processes.items():
            output_obj = client.get_output()
            outputs[name] = output_obj.lines
        return outputs
    
    def set_auto_restart(self, enabled: bool):
        """Enable or disable auto-restart."""
        self.auto_restart = enabled
        if enabled:
            self._start_watchdog()
        else:
            self._stop_watchdog()


class DaemonProcessManager(ProcessManager):
    """
    Process manager that runs as a daemon, listening on a socket.
    """
    
    def __init__(
        self,
        socket_path: str,
        session_name: str = "pyrmind",
        base_port: int = 5000,
        auto_restart: bool = False,
        restart_cooldown: float = 5.0,
        max_restart_count: int = 3
    ):
        super().__init__(
            session_name=session_name,
            base_port=base_port,
            auto_restart=auto_restart,
            restart_cooldown=restart_cooldown,
            max_restart_count=max_restart_count
        )
        self.socket_path = socket_path
        self.daemon_mode = True
    
    def handle_command(self, message) -> Dict[str, Any]:
        """Handle a command from the socket server."""
        command = message.command
        args = message.args
        
        if command == "start":
            return self._cmd_start(args)
        elif command == "restart":
            process = args.get('process')
            if not process:
                return {"status": "error", "error": "No process specified"}
            success = self.restart(process)
            return {"status": "ok" if success else "error", "process": process}
        elif command == "stop":
            process = args.get('process')
            if not process:
                return {"status": "error", "error": "No process specified"}
            success = self.stop(process)
            return {"status": "ok" if success else "error", "process": process}
        elif command == "status":
            return {"status": "ok", "info": self.get_status()}
        elif command == "kill":
            self.kill_all()
            return {"status": "ok"}
        elif command == "quit":
            self.kill_all()
            return {"status": "ok", "output": "Goodbye"}
        elif command == "autorestart":
            enabled = args.get('enabled')
            if enabled is None:
                return {"status": "error", "error": "No 'enabled' specified"}
            self.set_auto_restart(bool(enabled))
            return {"status": "ok", "auto_restart": self.auto_restart}
        elif command == "output":
            process = args.get('process')
            if not process:
                return {"status": "error", "error": "No process specified"}
            if process not in self.processes:
                return {"status": "error", "error": f"Process not found: {process}"}
            output_obj = self.tmux.get_output(process)
            return {"status": "ok", "lines": output_obj.lines}
        else:
            return {"status": "error", "error": f"Unknown command: {command}"}
    
    def _cmd_start(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Handle start command."""
        procfile_path = args.get('procfile')
        formation = args.get('formation')
        auto_restart = args.get('auto_restart', False)
        restart_cooldown = args.get('restart_cooldown', 5.0)
        max_restart_count = args.get('max_restart_count', 3)
        
        if not procfile_path:
            return {"status": "error", "error": "No procfile specified"}
        
        if not os.path.exists(procfile_path):
            return {"status": "error", "error": f"Procfile not found: {procfile_path}"}
        
        # Apply auto-restart settings
        self.auto_restart = auto_restart
        self.restart_cooldown = restart_cooldown
        self.max_restart_count = max_restart_count
        
        self.load_procfile(procfile_path, formation)
        self.start()
        
        return {
            "status": "ok",
            "processes": len(self.processes),
            "process_names": list(self.processes.keys()),
            "auto_restart": self.auto_restart
        }

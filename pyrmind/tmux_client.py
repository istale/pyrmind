"""Tmux client for Pyrmind using detached sessions.

Uses tmux new-session -d (without -CC) for process isolation and output capture.
This works in headless environments without a TTY.
"""
import subprocess
import os
import time
import signal
from typing import Optional, List, Dict, Any
from dataclasses import dataclass


@dataclass
class TmuxOutput:
    """Represents output from a tmux pane."""
    lines: List[str]
    exit_code: Optional[int] = None


class TmuxClient:
    """Client for tmux via detached sessions (no -CC flag).
    
    Pattern:
    - tmux new-session -d -s <name> -c <cwd> '<command>'
    - tmux send-keys -t <name> '<cmd>' C-m
    - tmux capture-pane -t <name> -p
    - tmux kill-session -t <name>
    """
    
    def __init__(self, session_name: str):
        self.session_name = session_name
        self.command: Optional[str] = None
        self.cwd: Optional[str] = None
        self.running = False
    
    def spawn(
        self,
        command: str,
        cwd: Optional[str] = None,
        env: Optional[Dict[str, str]] = None
    ) -> bool:
        """
        Spawn a process in a detached tmux session.
        
        Args:
            command: The command to run (as a string, will be run in bash)
            cwd: Working directory
            env: Environment variables
            
        Returns:
            True if started successfully
        """
        # Kill any existing session with this name
        subprocess.run(
            ['tmux', 'kill-session', '-t', self.session_name],
            stderr=subprocess.DEVNULL
        )
        
        self.command = command
        self.cwd = cwd
        self.running = True
        
        # Build tmux new-session command
        # tmux new-session -d -s <name> -c <cwd> '<command>'
        cmd = ['tmux', 'new-session', '-d', '-s', self.session_name]
        
        if cwd:
            cmd.extend(['-c', cwd])
        
        # The command runs in a login shell
        cmd.append(command)
        
        # Execute
        result = subprocess.run(cmd, capture_output=True)
        
        if result.returncode != 0:
            self.running = False
            return False
        
        return True
    
    def send_keys(self, cmd: str) -> bool:
        """Send keys to the tmux session."""
        if not self.running:
            return False
        
        result = subprocess.run(
            ['tmux', 'send-keys', '-t', self.session_name, cmd, 'Enter'],
            capture_output=True
        )
        return result.returncode == 0
    
    def capture_pane(self) -> List[str]:
        """Capture the current pane output as lines."""
        result = subprocess.run(
            ['tmux', 'capture-pane', '-t', self.session_name, '-p'],
            capture_output=True, text=True
        )
        
        if result.returncode != 0:
            return []
        
        return result.stdout.split('\n')
    
    def get_output(self) -> TmuxOutput:
        """Get current output from the pane."""
        lines = self.capture_pane()
        return TmuxOutput(lines=lines)
    
    def has_exited(self) -> bool:
        """Check if the session process has exited."""
        result = subprocess.run(
            ['tmux', 'list-sessions', '-t', self.session_name],
            capture_output=True
        )
        # If returncode != 0, session doesn't exist (exited)
        return result.returncode != 0
    
    def get_exit_code(self) -> Optional[int]:
        """Get the exit code if the session has exited."""
        if not self.has_exited():
            return None
        
        # Try to get exit code from last command
        result = subprocess.run(
            ['tmux', 'display-message', '-t', self.session_name, '-p', '#{session_exit_code}'],
            capture_output=True, text=True
        )
        
        if result.returncode == 0:
            try:
                return int(result.stdout.strip())
            except ValueError:
                pass
        
        return None
    
    def kill(self) -> bool:
        """Kill the tmux session."""
        self.running = False
        result = subprocess.run(
            ['tmux', 'kill-session', '-t', self.session_name],
            capture_output=True
        )
        return result.returncode == 0
    
    def resize_pane(self, width: int, height: int) -> bool:
        """Resize the pane to the given dimensions."""
        result = subprocess.run(
            ['tmux', 'resize-pane', '-t', self.session_name, 
             '-x', str(width), '-y', str(height)],
            capture_output=True
        )
        return result.returncode == 0


class TmuxProcessManager:
    """
    Manages multiple processes in separate tmux sessions.
    
    Each process gets its own tmux session with a unique name.
    This approach works in headless environments without a TTY.
    """
    
    def __init__(self, session_name: str = "pyrmind"):
        self.base_session_name = session_name
        self.processes: Dict[str, TmuxClient] = {}
    
    def _make_session_name(self, name: str) -> str:
        """Create a unique session name for a process."""
        return f"{self.base_session_name}-{name}"
    
    def spawn(
        self,
        name: str,
        command: str,
        cwd: Optional[str] = None,
        env: Optional[Dict[str, str]] = None
    ) -> bool:
        """
        Spawn a process in its own tmux session.
        
        Args:
            name: Unique name for this process
            command: Command to run
            cwd: Working directory
            env: Environment variables (currently not used, reserved for future)
            
        Returns:
            True if spawned successfully
        """
        session = self._make_session_name(name)
        client = TmuxClient(session)
        
        # Handle environment - we merge env into current process env
        # but tmux -d doesn't directly support env injection
        # For now, we rely on the process inheriting the current env
        if env:
            # Set env vars before spawning
            for k, v in env.items():
                os.environ[k] = v
        
        if not client.spawn(command, cwd=cwd):
            return False
        
        self.processes[name] = client
        return True
    
    def send_keys(self, name: str, cmd: str) -> bool:
        """Send keys to a process."""
        if name not in self.processes:
            return False
        return self.processes[name].send_keys(cmd)
    
    def capture_output(self, name: str) -> List[str]:
        """Get output from a process."""
        if name not in self.processes:
            return []
        return self.processes[name].capture_pane()
    
    def get_output(self, name: str) -> TmuxOutput:
        """Get output object from a process."""
        if name not in self.processes:
            return TmuxOutput(lines=[])
        return self.processes[name].get_output()
    
    def restart(
        self,
        name: str,
        command: str,
        cwd: Optional[str] = None,
        env: Optional[Dict[str, str]] = None
    ) -> bool:
        """Restart a specific process."""
        self.stop_process(name)
        return self.spawn(name, command, cwd, env)
    
    def stop_process(self, name: str) -> bool:
        """Stop a specific process."""
        if name not in self.processes:
            return False
        
        self.processes[name].kill()
        del self.processes[name]
        return True
    
    def kill_all(self):
        """Kill all processes and the tmux session."""
        for client in self.processes.values():
            client.kill()
        self.processes.clear()
        
        # Kill the base session if it exists
        subprocess.run(
            ['tmux', 'kill-session', '-t', self.base_session_name],
            stderr=subprocess.DEVNULL
        )
    
    def get_status(self) -> Dict[str, Any]:
        """Get status of all processes."""
        status = {}
        
        for name, client in self.processes.items():
            session = self._make_session_name(name)
            
            # Check if session exists
            result = subprocess.run(
                ['tmux', 'list-sessions', '-t', session],
                capture_output=True
            )
            
            running = result.returncode == 0
            
            status[name] = {
                'running': running,
                'session': session,
                'command': client.command,
                'cwd': client.cwd,
                'exit_code': client.get_exit_code() if not running else None
            }
        
        return status

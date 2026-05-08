"""Socket IPC server for Pyrmind daemon."""
import socket
import threading
import json
import os
from typing import Dict, Any, Optional, Callable
from dataclasses import dataclass


@dataclass
class DaemonMessage:
    """Represents a message from a client."""
    command: str
    args: Dict[str, Any]


class SocketServer:
    """
    Unix socket server for Pyrmind daemon commands.
    
    Protocol:
    - Client connects and sends: command\n args_json\n
    - Server responds with JSON response
    """
    
    def __init__(self, socket_path: str):
        self.socket_path = socket_path
        self.server_socket: Optional[socket.socket] = None
        self.running = False
        self.handler: Optional[Callable] = None
        self._thread: Optional[threading.Thread] = None
    
    def set_handler(self, handler: Callable[[DaemonMessage], Dict[str, Any]]):
        """Set the message handler function."""
        self.handler = handler
    
    def start(self):
        """Start the socket server."""
        # Remove existing socket file
        if os.path.exists(self.socket_path):
            os.remove(self.socket_path)
        
        self.server_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.server_socket.bind(self.socket_path)
        self.server_socket.listen(5)
        self.server_socket.settimeout(1)  # Allow periodic checks for shutdown
        
        os.chmod(self.socket_path, 0o600)
        
        self.running = True
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()
    
    def _serve(self):
        """Main server loop."""
        while self.running:
            try:
                client, _ = self.server_socket.accept()
                threading.Thread(
                    target=self._handle_client,
                    args=(client,),
                    daemon=True
                ).start()
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    pass  # Log error in production
    
    def _handle_client(self, client: socket.socket):
        """Handle a single client connection."""
        try:
            client.settimeout(10)
            
            # Read command
            command_data = b''
            while b'\n' not in command_data:
                chunk = client.recv(4096)
                if not chunk:
                    return
                command_data += chunk
            
            command_line, rest = command_data.split(b'\n', 1)
            command = command_line.decode('utf-8').strip()
            
            # Read args (rest might contain them)
            try:
                args = json.loads(rest.decode('utf-8')) if rest.strip() else {}
            except json.JSONDecodeError:
                args = {}
            
            # Process message
            if self.handler:
                response = self.handler(DaemonMessage(command=command, args=args))
            else:
                response = {"status": "error", "error": "No handler set"}
            
            # Send response
            response_data = json.dumps(response) + '\n'
            client.sendall(response_data.encode('utf-8'))
        
        except Exception as e:
            try:
                error_response = json.dumps({"status": "error", "error": str(e)}) + '\n'
                client.sendall(error_response.encode('utf-8'))
            except Exception:
                pass
        finally:
            client.close()
    
    def stop(self):
        """Stop the socket server."""
        self.running = False
        
        if self.server_socket:
            try:
                self.server_socket.close()
            except Exception:
                pass
            self.server_socket = None
        
        if os.path.exists(self.socket_path):
            try:
                os.remove(self.socket_path)
            except Exception:
                pass


class SocketClient:
    """Client for connecting to Pyrmind socket server."""
    
    def __init__(self, socket_path: str):
        self.socket_path = socket_path
    
    def send_command(self, command: str, **kwargs) -> Dict[str, Any]:
        """
        Send a command to the daemon.
        
        Args:
            command: Command name (start, restart, stop, status, kill, quit)
            **kwargs: Additional arguments
        
        Returns:
            Response dict from daemon
        """
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            sock.connect(self.socket_path)
            
            # Send command
            msg = command + '\n' + json.dumps(kwargs) + '\n'
            sock.sendall(msg.encode('utf-8'))
            
            # Receive response
            response_data = b''
            while True:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                response_data += chunk
                if b'\n' in response_data:
                    break
            
            if response_data:
                return json.loads(response_data.decode('utf-8'))
            else:
                return {"status": "error", "error": "No response"}
        
        except FileNotFoundError:
            return {"status": "error", "error": f"Socket not found: {self.socket_path}"}
        except ConnectionRefusedError:
            return {"status": "error", "error": "Connection refused - daemon not running?"}
        except Exception as e:
            return {"status": "error", "error": str(e)}
        finally:
            sock.close()
    
    def start(self, **kwargs) -> Dict[str, Any]:
        return self.send_command("start", **kwargs)
    
    def restart(self, process: str, **kwargs) -> Dict[str, Any]:
        return self.send_command("restart", process=process, **kwargs)
    
    def stop(self, process: str, **kwargs) -> Dict[str, Any]:
        return self.send_command("stop", process=process, **kwargs)
    
    def status(self, **kwargs) -> Dict[str, Any]:
        return self.send_command("status", **kwargs)
    
    def kill(self, **kwargs) -> Dict[str, Any]:
        return self.send_command("kill", **kwargs)
    
    def quit(self, **kwargs) -> Dict[str, Any]:
        return self.send_command("quit", **kwargs)

    def autorestart(self, enabled: bool = True, **kwargs) -> Dict[str, Any]:
        return self.send_command("autorestart", enabled=enabled, **kwargs)

    def output(self, process: str, **kwargs) -> Dict[str, Any]:
        return self.send_command("output", process=process, **kwargs)

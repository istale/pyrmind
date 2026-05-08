"""Pyrmind - Python process manager for Procfile-based applications.

A Python clone of Overmind, using tmux for process isolation and output capture.
"""
import sys
import os
import argparse
import signal
import time

from .socket_server import SocketServer, SocketClient
from .process_manager import DaemonProcessManager
import pyrmind


def run_daemon(
    socket_path: str,
    procfile: str,
    formation: str,
    base_port: int,
    auto_restart: bool,
    restart_cooldown: float,
    max_restart_count: int
):
    """Run as a daemon process."""
    manager = DaemonProcessManager(
        socket_path=socket_path,
        base_port=base_port,
        auto_restart=auto_restart,
        restart_cooldown=restart_cooldown,
        max_restart_count=max_restart_count
    )
    
    # Setup socket server with command handler
    server = SocketServer(socket_path)
    server.set_handler(manager.handle_command)
    server.start()
    
    # Load and start if procfile provided
    if procfile:
        if os.path.exists(procfile):
            manager.load_procfile(procfile, formation)
            manager.start()
            print(f"Started {len(manager.processes)} processes from {procfile}")
            if auto_restart:
                print(f"Auto-restart enabled (cooldown: {restart_cooldown}s, max: {max_restart_count})")
        else:
            print(f"Warning: Procfile not found: {procfile}")
    
    print(f"Pyrmind daemon running on {socket_path}")
    print("Press Ctrl+C to stop...")
    
    # Handle signals
    def signal_handler(sig, frame):
        print("\nShutting down...")
        manager.kill_all()
        server.stop()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Keep alive
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        manager.kill_all()
        server.stop()


def run_client(socket_path: str, command: str, **kwargs):
    """Run a client command."""
    if not os.path.exists(socket_path):
        print(f"Error: Socket not found: {socket_path}")
        print("Is the daemon running?")
        sys.exit(1)
    
    client = SocketClient(socket_path)
    
    if command == "start":
        result = client.start(**kwargs)
    elif command == "restart":
        result = client.restart(process=kwargs.get('process', ''))
    elif command == "stop":
        result = client.stop(process=kwargs.get('process', ''))
    elif command == "status":
        result = client.status()
    elif command == "kill":
        result = client.kill()
    elif command == "quit":
        result = client.quit()
    elif command == "autorestart":
        result = client.autorestart(enabled=kwargs.get('enabled', True))
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)
    
    # Print result
    if result.get('status') == 'ok':
        if 'output' in result:
            print(result['output'])
        elif 'processes' in result:
            print(f"Started {result['processes']} processes:")
            for name in result.get('process_names', []):
                print(f"  - {name}")
            if result.get('auto_restart'):
                print(f"Auto-restart: enabled")
        elif 'info' in result:
            print("Process status:")
            for name, info in result['info'].items():
                status = "running" if info.get('running') else "stopped"
                restart_info = ""
                if info.get('auto_restart'):
                    restart_info = f" [restart_count={info.get('restart_count', 0)}]"
                can_die = " (can_die)" if info.get('can_die') else ""
                print(f"  - {name}: {status}{can_die}{restart_info}")
        elif 'auto_restart' in result:
            print(f"Auto-restart: {'enabled' if result['auto_restart'] else 'disabled'}")
        else:
            print("OK")
    else:
        print(f"Error: {result.get('error', 'Unknown error')}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Pyrmind - Python process manager for Procfile-based applications",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument('--version', action='version', version=f'%(prog)s {pyrmind.__version__}')
    
    subparsers = parser.add_subparsers(dest='command', help='Commands')
    
    # Daemon commands
    start_parser = subparsers.add_parser('start', help='Start as daemon')
    start_parser.add_argument('-s', '--socket', default='~/.pyrmind/pyrmind.sock',
                            help='Socket path')
    start_parser.add_argument('-f', '--procfile', default='Procfile',
                            help='Procfile path')
    start_parser.add_argument('-m', '--formation', 
                            help='Formation (e.g., web=2,worker=3)')
    start_parser.add_argument('-p', '--base-port', type=int, default=5000,
                            help='Base port for PORT formation')
    start_parser.add_argument('--auto-restart', action='store_true',
                            help='Enable auto-restart for crashed processes')
    start_parser.add_argument('--no-auto-restart', dest='auto_restart', action='store_false',
                            help='Disable auto-restart (default)')
    start_parser.add_argument('--restart-cooldown', type=float, default=5.0,
                            help='Seconds to wait before restarting crashed process (default: 5.0)')
    start_parser.add_argument('--max-restart-count', type=int, default=3,
                            help='Max restart attempts per process (0=infinite, default: 3)')
    
    restart_parser = subparsers.add_parser('restart', help='Restart a process')
    restart_parser.add_argument('process', nargs='?', help='Process name')
    restart_parser.add_argument('-s', '--socket', default='~/.pyrmind/pyrmind.sock',
                               help='Socket path')
    
    stop_parser = subparsers.add_parser('stop', help='Stop a process')
    stop_parser.add_argument('process', nargs='?', help='Process name')
    stop_parser.add_argument('-s', '--socket', default='~/.pyrmind/pyrmind.sock',
                            help='Socket path')
    
    status_parser = subparsers.add_parser('status', help='Show status')
    status_parser.add_argument('-s', '--socket', default='~/.pyrmind/pyrmind.sock',
                              help='Socket path')
    
    kill_parser = subparsers.add_parser('kill', help='Kill all processes')
    kill_parser.add_argument('-s', '--socket', default='~/.pyrmind/pyrmind.sock',
                             help='Socket path')
    
    quit_parser = subparsers.add_parser('quit', help='Shutdown daemon')
    quit_parser.add_argument('-s', '--socket', default='~/.pyrmind/pyrmind.sock',
                             help='Socket path')
    
    autorestart_parser = subparsers.add_parser('autorestart', help='Enable/disable auto-restart at runtime')
    autorestart_parser.add_argument('enabled', nargs='?', choices=['on', 'off'],
                                   help='Turn auto-restart on or off')
    autorestart_parser.add_argument('-s', '--socket', default='~/.pyrmind/pyrmind.sock',
                                    help='Socket path')
    
    attach_parser = subparsers.add_parser('attach', help='Attach to aggregated log view')
    attach_parser.add_argument('-s', '--socket', default='~/.pyrmind/pyrmind.sock',
                             help='Socket path')
    attach_parser.add_argument('--poll-interval', type=float, default=0.5,
                             help='Poll interval in seconds (default: 0.5)')
    
    # Version
    version_parser = subparsers.add_parser('version', help='Show version')
    
    args = parser.parse_args()
    
    if args.command is None:
        parser.print_help()
        sys.exit(1)
    
    if args.command == 'version':
        print(f"Pyrmind {pyrmind.__version__}")
        sys.exit(0)
    
    # Expand socket path
    socket_path = os.path.expanduser(args.socket if hasattr(args, 'socket') else '~/.pyrmind/pyrmind.sock')
    
    if args.command == 'start':
        procfile = args.procfile if hasattr(args, 'procfile') else 'Procfile'
        formation = args.formation if hasattr(args, 'formation') else None
        base_port = args.base_port if hasattr(args, 'base_port') else 5000
        auto_restart = args.auto_restart if hasattr(args, 'auto_restart') else False
        restart_cooldown = args.restart_cooldown if hasattr(args, 'restart_cooldown') else 5.0
        max_restart_count = args.max_restart_count if hasattr(args, 'max_restart_count') else 3
        
        run_daemon(socket_path, procfile, formation, base_port, auto_restart, restart_cooldown, max_restart_count)
    
    elif args.command == 'autorestart':
        enabled = None
        if args.enabled == 'on':
            enabled = True
        elif args.enabled == 'off':
            enabled = False
        
        run_client(socket_path, 'autorestart', enabled=enabled)
    
    elif args.command == 'attach':
        from .attach import start_attach
        poll_interval = getattr(args, 'poll_interval', 0.5)
        start_attach(socket_path, poll_interval=poll_interval)
    
    elif args.command in ('restart', 'stop', 'status', 'kill', 'quit'):
        cmd = args.command
        kwargs = {}
        
        if cmd in ('restart', 'stop'):
            if not args.process:
                print(f"Error: {cmd} requires a process name")
                sys.exit(1)
            kwargs['process'] = args.process
        
        run_client(socket_path, cmd, **kwargs)
    
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == '__main__':
    main()

# Pyrmind

A Python implementation of Overmind — process manager for Procfile-based applications using tmux.

**Status**: Beta - In Development

## Features

- **tmux control mode**: Real-time output capture without file-based lag
- **Socket IPC**: Daemon mode with Unix socket commands
- **Procfile parsing**: Standard format with process scaling (`web=2,worker=3`)
- **Port formation**: Automatic PORT and OVERMIND_PROCESS_*_PORT environment variables
- **can-die mechanism**: Non-essential processes can exit without stopping the stack
- **Auto-restart**: Optional automatic restart of crashed processes (configurable cooldown and max attempts)
- **Process isolation**: Restart individual processes without affecting others

## Installation

```bash
# From source
cd /path/to/pyrmind
pip install -e .
# or
uv pip install -e .

# From PyPI (when published)
pip install pyrmind
uv pip install pyrmind
```

## Usage

### Start Daemon

```bash
# Basic start
pyrmind start -f Procfile

# With auto-restart
pyrmind start -f Procfile --auto-restart --restart-cooldown 2 --max-restart-count 5

# With process scaling
pyrmind start -f Procfile -m web=2,worker=3

# With custom port base
pyrmind start -f Procfile -p 7000
```

### Run Commands (while daemon is running)

```bash
# Check status
pyrmind status

# Restart a process
pyrmind restart web

# Stop a process
pyrmind stop worker

# Enable/disable auto-restart at runtime
pyrmind autorestart on
pyrmind autorestart off

# Kill everything
pyrmind kill

# Shutdown daemon
pyrmind quit
```

### Procfile Format

```procfile
web:     python app.py
worker:  python worker.py
assets:  python assets.py
```

With scaling:
```bash
pyrmind start -f Procfile -m web=2,worker=3
```

With port formation:
```bash
pyrmind start -f Procfile -p 7000
```

### can_die Mechanism

Processes marked as `can_die` can exit without stopping the stack (they will NOT be auto-restarted):

```procfile
assets: python assets.py  # can_die
```

### Auto-Restart

When `--auto-restart` is enabled, pyrmind will automatically restart crashed processes:

- `--restart-cooldown N`: Seconds to wait before restarting (default: 5.0)
- `--max-restart-count N`: Max restart attempts per process before giving up (0=infinite, default: 3)

Example:
```bash
pyrmind start -f Procfile --auto-restart --restart-cooldown 1 --max-restart-count 5
```

## CLI Options

```
start:
  -f, --procfile PATH       Procfile path (default: Procfile)
  -m, --formation TEXT      Process scaling (e.g., web=2,worker=3)
  -p, --base-port N         Base port for PORT formation (default: 5000)
  -s, --socket PATH         Socket path (default: ~/.pyrmind/pyrmind.sock)
  --auto-restart            Enable auto-restart for crashed processes
  --restart-cooldown SEC    Seconds to wait before restarting (default: 5.0)
  --max-restart-count N     Max restarts per process, 0=infinite (default: 3)

autorestart:
  on/off                    Enable or disable auto-restart at runtime

Other commands:
  restart [process]         Restart a process
  stop [process]            Stop a process
  status                    Show process status
  kill                      Kill all processes
  quit                      Shutdown daemon
```

## Architecture

```
pyrmind/
├── pyrmind/
│   ├── __init__.py       # Package exports
│   ├── __main__.py       # CLI entry point
│   ├── procfile.py       # Procfile parsing
│   ├── tmux_client.py    # tmux control mode wrapper
│   ├── process_manager.py # Process lifecycle + auto-restart watchdog
│   ├── socket_server.py  # Unix socket IPC
│   └── env.py            # Environment variable injection
├── experiments/          # Test experiments
│   └── smoke_test/
├── pyproject.toml        # Modern Python packaging
└── README.md
```

## Overmind Compatibility

Pyrmind aims to be compatible with Overmind's CLI interface:

| Overmind | Pyrmind | Notes |
|----------|---------|-------|
| `overmind start -s sock` | `pyrmind start -s sock` | |
| `overmind restart web` | `pyrmind restart web -s sock` | |
| `overmind stop assets` | `pyrmind stop assets -s sock` | |
| `overmind status` | `pyrmind status -s sock` | |
| `overmind kill` | `pyrmind kill -s sock` | |

## Differences from Overmind

- Written in Python instead of Go
- Socket protocol is JSON instead of custom binary format
- No support for Overmind's file-based output (always tmux)
- Auto-restart is configurable (Overmind uses fixed behavior)

## License

MIT
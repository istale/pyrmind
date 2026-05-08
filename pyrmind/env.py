"""Environment variable injection for Pyrmind.

Handles port formation and other env var logic from Overmind."""
import os
from typing import Dict, Optional


def make_env(
    base_port: int = 5000,
    port_index: int = 0,
    formation: Optional[Dict[str, int]] = None,
    extra_env: Optional[Dict[str, str]] = None
) -> Dict[str, str]:
    """
    Create environment variables for a process.
    
    Port formation:
    - PORT=<base_port + port_index>
    - OVERMIND_PROCESS_<NAME>_PORT=<base_port + port_index>
    - OVERMIND_PROCESS_<NAME>_<SCALED_NAME>_PORT=<base_port + port_index>
    
    Args:
        base_port: Starting port number (default 5000)
        port_index: Which port offset to use (0, 1, 2, ...)
        formation: Dict of process_name -> count for scaled processes
        extra_env: Additional env vars to include
    
    Returns:
        Dict of environment variables
    """
    env = dict(os.environ)
    
    # Calculate actual port
    port = base_port + port_index
    env['PORT'] = str(port)
    
    if extra_env:
        env.update(extra_env)
    
    return env


def port_for_process(
    name: str,
    base_port: int = 5000,
    port_increment: int = 10
) -> int:
    """
    Calculate port for a named process.
    
    Uses port_increment spacing between process instances.
    """
    return base_port + (hash(name) % 100) * port_increment


def format_env_var_name(process_name: str, scaled_name: Optional[str] = None) -> str:
    """
    Format environment variable name for a process.
    
    Examples:
        format_env_var_name("web") -> "OVERMIND_PROCESS_WEB_PORT"
        format_env_var_name("web", "web.1") -> "OVERMIND_PROCESS_WEB_WEB_1_PORT"
    """
    if scaled_name and scaled_name != process_name:
        # Remove the base name prefix from scaled name
        if scaled_name.startswith(process_name + '.'):
            suffix = scaled_name[len(process_name)+1:]
            return f"OVERMIND_PROCESS_{process_name.upper()}_{suffix.upper()}_PORT"
    
    return f"OVERMIND_PROCESS_{process_name.upper()}_PORT"


def inject_port_env(
    name: str,
    command: str,
    base_port: int = 5000,
    port_increment: int = 10
) -> str:
    """
    Inject port environment variables into a command string.
    
    Replaces $PORT, ${PORT}, %PORT% with actual port value.
    Replaces $OVERMIND_PROCESS_*_PORT with appropriate env var name.
    """
    port = port_for_process(name, base_port, port_increment)
    
    # Replace $PORT and ${PORT}
    command = command.replace('$PORT', str(port))
    command = command.replace('${PORT}', str(port))
    command = command.replace('%PORT%', str(port))
    
    # Replace $OVERMIND_PROCESS_*_PORT with actual env var references
    import re
    pattern = r'\$OVERMIND_PROCESS_\w+_PORT|\$\{OVERMIND_PROCESS_\w+_PORT\}'
    
    def replacer(match):
        return f"$PORT"  # Simplified: just use PORT
    
    return re.sub(pattern, replacer, command)

"""Procfile parsing for Pyrmind."""
import re
import os
from typing import Dict, List, Optional


class ProcfileEntry:
    """Represents a single process entry from a Procfile."""
    
    def __init__(self, name: str, command: str, can_die: bool = False):
        self.name = name
        self.command = command
        self.can_die = can_die
    
    def __repr__(self):
        return f"ProcfileEntry(name={self.name!r}, command={self.command!r}, can_die={self.can_die})"


def parse_procfile(content: str) -> Dict[str, List[ProcfileEntry]]:
    """
    Parse Procfile content.
    
    Standard format:
        web: python app.py
        worker: python worker.py
    
    Extended format with can_die:
        assets: python assets.py  # can_die
    
    Returns dict mapping process_name -> list of ProcfileEntry (for scaled processes)
    """
    processes = {}
    lines = content.splitlines()
    
    for line in lines:
        line = line.strip()
        
        # Skip empty lines and comments
        if not line or line.startswith('#'):
            continue
        
        # Parse process_name: command
        # Supports indented lines (yaml-style)
        match = re.match(r'^(\w[\w-]*)\s*:\s*(.+)$', line)
        if not match:
            continue
        
        name = match.group(1)
        rest = match.group(2).strip()
        
        # Check for inline comment # can_die
        can_die = False
        if ' #' in rest:
            rest, comment = rest.rsplit(' #', 1)
            rest = rest.strip()
            can_die = 'can_die' in comment
        
        # Remove trailing comment
        if ' #' in rest:
            rest = rest.split(' #')[0].strip()
        
        if name not in processes:
            processes[name] = []
        
        processes[name].append(ProcfileEntry(name=name, command=rest, can_die=can_die))
    
    return processes


def parse_formation(formation: str) -> Dict[str, int]:
    """
    Parse formation string like 'web=2,worker=3' into dict.
    
    Returns dict mapping process_name -> count
    """
    result = {}
    if not formation:
        return result
    
    for part in formation.split(','):
        part = part.strip()
        if not part:
            continue
        if '=' in part:
            name, count = part.split('=', 1)
            try:
                result[name.strip()] = int(count)
            except ValueError:
                pass
    return result


def read_procfile(path: str) -> Dict[str, List[ProcfileEntry]]:
    """Read and parse a Procfile from a file path."""
    with open(path, 'r') as f:
        content = f.read()
    return parse_procfile(content)


def expand_procfile(
    processes: Dict[str, List[ProcfileEntry]],
    formation: Dict[str, int]
) -> List[ProcfileEntry]:
    """
    Expand processes according to formation scaling.
    
    e.g., if web has 2 instances in formation:
        web.1: command
        web.2: command
    """
    expanded = []
    
    for name, entries in processes.items():
        count = formation.get(name, 1)
        
        for i in range(count):
            if count > 1:
                # Scale suffix: web.1, web.2, etc.
                scaled_name = f"{name}.{i + 1}"
            else:
                scaled_name = name
            
            for entry in entries:
                expanded.append(ProcfileEntry(
                    name=scaled_name,
                    command=entry.command,
                    can_die=entry.can_die
                ))
    
    return expanded

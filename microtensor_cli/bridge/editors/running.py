from __future__ import annotations

import subprocess
import sys
from collections.abc import Mapping


def running(processes: Mapping[str, str]) -> bool:
    name = processes.get(sys.platform) or processes.get("linux", "")
    if not name:
        return False
    try:
        if sys.platform == "win32":
            found = subprocess.run(
                ["tasklist", "/FI", f"IMAGENAME eq {name}", "/NH", "/FO", "CSV"],
                capture_output=True,
                text=True,
                check=False,
                timeout=20,
            )
            return f'"{name.lower()}"' in found.stdout.lower()
        found = subprocess.run(["pgrep", "-x", name], capture_output=True, check=False, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return found.returncode == 0

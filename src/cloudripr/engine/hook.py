"""The --notification-script hook.

icloudpd runs this script synchronously right after detecting that 2FA is
required and BEFORE asking Apple to push a code. We drop a marker for the
app and block; the app then kills the whole process group, so an unattended
run never triggers a push to the user's devices.

The script must never return before it is killed: upstream swallows hook
errors and would go on to request the push. So the marker is created with a
regular builtin (``true``), because a failed redirection on a POSIX special
builtin such as ``:`` makes a non-interactive sh exit, and the wait is a loop
rather than ``exec`` (a failed exec also ends the script).
"""

from __future__ import annotations

import uuid
from pathlib import Path


MARKER_ENV = "CLOUDRIPR_2FA_MARKER"

HOOK_SCRIPT = f"""#!/bin/sh
# Installed by cloudripr. See cloudripr/engine/hook.py.
true 2>/dev/null > "${MARKER_ENV}"
while :; do sleep 60 2>/dev/null || :; done
"""


def install_hook(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.is_file() or path.read_text() != HOOK_SCRIPT:
        path.write_text(HOOK_SCRIPT)
    path.chmod(0o755)
    return path


def new_marker(directory: Path) -> Path:
    return directory / f"{uuid.uuid4().hex}.marker"

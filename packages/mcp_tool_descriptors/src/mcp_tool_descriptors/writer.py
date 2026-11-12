"""Replace the record atomically so an interrupted run cannot truncate it.

A same-directory temporary file is fsynced and renamed over the record, so a
failed write leaves the original in place and no temporary file behind. The mode
is not forced — git records only the executable bit, so the temporary file's
0600 commits as the same 100644 record.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from mcp_tool_descriptors.paths import confine


def write_atomic(path: Path, record: dict[str, Any], allow_root: Path | None = None) -> None:
    """Write ``record`` to ``path``, replacing it only once the bytes are on disk."""
    target = confine(path, allow_root)
    payload = json.dumps(record, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    target.parent.mkdir(parents=True, exist_ok=True)
    handle, temp_name = tempfile.mkstemp(
        dir=target.parent, prefix=f".{target.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, target)
    except BaseException:
        Path(temp_name).unlink(missing_ok=True)
        raise

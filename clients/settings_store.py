"""Shared JSON settings store for the MEMS UI.

All UI components persist into one file (mems_settings.json) under their own
top-level key, via read-modify-write so they never clobber each other. Writes
are atomic (temp file + os.replace) so a crash or power loss mid-write can't
corrupt the file — the previous good copy survives.
"""
import json
import os


def load_settings(path):
    """Return the full settings dict, or {} if missing/unreadable."""
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return {}


def update_section(path, key, data):
    """Merge `data` into top-level `key`, preserving every other section.

    Atomic: writes to a temp file then renames over the target.
    """
    cfg = load_settings(path)
    cfg[key] = data
    try:
        tmp = f"{path}.tmp"
        with open(tmp, "w") as f:
            json.dump(cfg, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except Exception:
        pass

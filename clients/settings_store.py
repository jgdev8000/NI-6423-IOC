"""Shared JSON settings store for the MEMS UI.

All UI components persist into one file (mems_settings.json) under their own
top-level key, via read-modify-write so they never clobber each other. Writes
are atomic (temp file + os.replace) so a crash or power loss mid-write can't
corrupt the file — the previous good copy survives.
"""
import json
import os
import sys


def default_path(filename="mems_settings.json"):
    """Return a persistent, writable path for the settings file.

    In a normal (source) run this sits next to the code. In a frozen PyInstaller
    build, __file__ points into the temporary _MEIPASS extraction dir that is
    deleted on exit, so settings written there are lost. When frozen, prefer a
    folder next to the .exe (portable) if it is writable, else fall back to a
    per-user app-data directory.
    """
    if getattr(sys, "frozen", False):
        appdata = os.environ.get("APPDATA") or os.path.expanduser("~")
        candidates = [os.path.dirname(sys.executable),
                      os.path.join(appdata, "MEMS-UI")]
    else:
        candidates = [os.path.dirname(os.path.abspath(__file__))]
    for d in candidates:
        try:
            os.makedirs(d, exist_ok=True)
            probe = os.path.join(d, ".write_test")
            with open(probe, "w") as f:
                f.write("")
            os.remove(probe)
            return os.path.join(d, filename)
        except Exception:
            continue
    return os.path.join(os.path.expanduser("~"), filename)  # last resort


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
    except Exception as exc:
        # Don't crash the UI on a write failure, but don't hide it either.
        print(f"settings_store: could not write {path}: {exc}", file=sys.stderr)

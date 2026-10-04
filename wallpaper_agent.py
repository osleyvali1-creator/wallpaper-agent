#!/usr/bin/env python3
"""
wallpaper-agent
===============
Cross-platform wallpaper agent with a shared schedule layer and OS-specific
execution backends.

Supported backends:
- macOS: native AppleScript Finder wallpaper switching and aerial support
- Windows: static wallpaper support via Win32 API, and video/live wallpaper via
  Lively Wallpaper if installed

Usage:
    python3 wallpaper_agent.py --daemon
    python3 wallpaper_agent.py --apply-now
    python3 wallpaper_agent.py --status
    python3 wallpaper_agent.py --list
    python3 wallpaper_agent.py --set "C:/Pictures/wallpaper.jpg"
"""
import argparse
import json
import os
import platform
import shutil
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.json"
STATE_PATH = BASE_DIR / ".state.json"

DEFAULT_CONFIG = {
    "check_interval_seconds": 60,
    "apply_on_start": True,
    "wallpaper_dir": "wallpapers",
    "schedule": [
        {"time": "06:00", "label": "Morning", "wallpaper": "morning.jpg"},
        {"time": "12:00", "label": "Midday", "wallpaper": "midday.jpg"},
        {"time": "17:30", "label": "Evening", "wallpaper": "evening.jpg"},
        {"time": "21:00", "label": "Night", "wallpaper": "night.jpg"},
    ],
}

_running = True


def log(msg, err=False):
    line = f"[{datetime.now().isoformat(timespec='seconds')}] {msg}"
    print(line, file=sys.stderr if err else sys.stdout, flush=True)


def load_config():
    if not CONFIG_PATH.exists():
        CONFIG_PATH.write_text(json.dumps(DEFAULT_CONFIG, indent=2) + "\n")
    with CONFIG_PATH.open() as fh:
        return json.load(fh)


def read_state():
    try:
        return json.loads(STATE_PATH.read_text())
    except Exception:
        return {}


def write_state(state):
    try:
        STATE_PATH.write_text(json.dumps(state, indent=2) + "\n")
    except Exception as exc:
        log(f"could not write state: {exc}", err=True)


def parse_hhmm(value):
    parts = str(value).split(":")
    if len(parts) != 2:
        raise ValueError(f"bad time '{value}', expected 'HH:MM'")
    hh, mm = int(parts[0]), int(parts[1])
    if not (0 <= hh <= 23 and 0 <= mm <= 59):
        raise ValueError(f"bad time '{value}'")
    return hh * 60 + mm


def sorted_schedule(cfg):
    return sorted(cfg.get("schedule", []), key=lambda e: parse_hhmm(e["time"]))


def active_slot(cfg, now=None):
    now = now or datetime.now()
    schedule = sorted_schedule(cfg)
    if not schedule:
        return None
    now_min = now.hour * 60 + now.minute
    chosen = None
    for entry in schedule:
        if parse_hhmm(entry["time"]) <= now_min:
            chosen = entry
        else:
            break
    return chosen or schedule[-1]


def resolve_wallpaper_path(entry, cfg):
    raw = entry.get("wallpaper")
    if not raw:
        return None
    p = Path(os.path.expanduser(raw))
    if not p.is_absolute():
        p = BASE_DIR / cfg.get("wallpaper_dir", "wallpapers") / p
    return p


def slot_target(slot, cfg):
    if slot.get("aerial"):
        return f"aerial:{slot['aerial']}"
    return str(resolve_wallpaper_path(slot, cfg))


# --------------------------------------------------------------------------- #
# Platform-specific implementations
# --------------------------------------------------------------------------- #

def _run_command(cmd):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=30)


def set_macos_wallpaper(path):
    path = str(Path(path))
    script = f'tell application "Finder" to set desktop picture to POSIX file "{path}"'
    res = _run_command(["/usr/bin/osascript", "-e", script])
    return res.returncode == 0


def set_macos_aerial(asset_id, appearance="automatic", sync_screensaver=True):
    """Placeholder for the existing dynamic aerial implementation. Keep this in
    the macOS-specific branch if you later want to wire in the full native aerial
    functionality from your original script."""
    log(f"macOS aerial handling requested for {asset_id}; use the advanced native implementation here.", err=True)
    return False


def set_windows_wallpaper(path):
    """Set a static wallpaper on Windows, or a live wallpaper if Lively is present."""
    path = str(Path(path).expanduser().resolve())
    if not os.path.exists(path):
        log(f"wallpaper file missing: {path}", err=True)
        return False

    lively = shutil.which("livelyw")
    ext = Path(path).suffix.lower()
    if lively and ext in {".mp4", ".mov", ".webm", ".mkv", ".avi"}:
        try:
            res = _run_command([lively, "--setwallpaper", path])
            if res.returncode == 0:
                return True
            log(f"Lively wallpaper fallback failed: {res.stderr.strip()}", err=True)
        except Exception as exc:
            log(f"Lively wallpaper call failed: {exc}", err=True)

    try:
        import ctypes
        SPI_SETDESKWALLPAPER = 20
        ctypes.windll.user32.SystemParametersInfoW(SPI_SETDESKWALLPAPER, 0, path, 3)
        return True
    except Exception as exc:
        log(f"Windows wallpaper API failed: {exc}", err=True)
        return False


def set_wallpaper(path, entry=None):
    """Platform abstraction: delegate to the correct backend for the current OS."""
    system = platform.system()
    if system == "Darwin":
        if entry and entry.get("aerial"):
            asset_id = entry["aerial"]
            return set_macos_aerial(asset_id, entry.get("appearance", "automatic"), True)
        return set_macos_wallpaper(path)
    if system == "Windows":
        return set_windows_wallpaper(path)
    log(f"unsupported platform for wallpaper switching: {system}", err=True)
    return False


def get_current_wallpaper():
    system = platform.system()
    if system == "Darwin":
        try:
            res = _run_command(["/usr/bin/osascript", "-e", 'tell application "Finder" to get desktop picture'])
            if res.returncode == 0:
                return res.stdout.strip() or None
        except Exception as exc:
            log(f"get_current_wallpaper failed: {exc}", err=True)
        return None
    if system == "Windows":
        # Best-effort only; Windows does not expose a simple desktop-picture script
        # via a stable CLI.
        return None
    return None


def apply_current(cfg, force=False):
    slot = active_slot(cfg)
    if slot is None:
        log("no schedule configured", err=True)
        return False

    label = slot.get("label", slot["time"])
    target = slot_target(slot, cfg)
    state = read_state()
    key = f'{slot["time"]}|{target}'
    if not force and state.get("applied_key") == key:
        return False

    path = resolve_wallpaper_path(slot, cfg)
    if path and not path.exists():
        log(f"skipping '{label}': wallpaper not found ({path})", err=True)
        return False

    if path is None:
        log(f"skipping '{label}': no wallpaper path defined", err=True)
        return False

    ok = set_wallpaper(path, slot)
    if ok:
        log(f"applied '{label}' ({slot['time']}) -> {target}")
        state.update({
            "applied_key": key,
            "applied_at": datetime.now().isoformat(timespec="seconds"),
            "label": label,
            "time": slot["time"],
            "target": target,
        })
        write_state(state)
        return True

    log(f"failed to apply '{label}' -> {target}", err=True)
    return False


def print_status(cfg):
    slot = active_slot(cfg)
    state = read_state()
    current = get_current_wallpaper()
    if slot:
        log(f"active slot : {slot.get('label', slot['time'])} ({slot['time']}) -> {slot_target(slot, cfg)}")
    else:
        log("active slot : none configured", err=True)
    log(f"current     : {current or 'unknown'}")
    if state.get("applied_at"):
        log(f"last applied: {state.get('label')} at {state.get('applied_at')}")
    else:
        log("last applied: never")


def print_schedule(cfg):
    schedule = sorted_schedule(cfg)
    if not schedule:
        log("no schedule configured", err=True)
        return
    for entry in schedule:
        if entry.get("aerial"):
            log(f"  {entry['time']}  {entry.get('label', '')} [aerial] {entry['aerial']}")
        else:
            p = resolve_wallpaper_path(entry, cfg)
            exists = "ok" if p and p.exists() else "MISSING"
            log(f"  {entry['time']}  {entry.get('label', '')} [{exists:>7}] {p}")


def _handle_signal(signum, _frame):
    global _running
    _running = False
    log(f"received signal {signum}; shutting down")


def run_daemon(cfg):
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)
    log("daemon started")
    if cfg.get("apply_on_start", True):
        apply_current(cfg, force=True)
    while _running:
        try:
            cfg = load_config()
        except Exception as exc:
            log(f"config reload failed: {exc}", err=True)
        apply_current(cfg)
        interval = max(5, int(cfg.get("check_interval_seconds", 60)))
        time.sleep(interval)
    log("daemon stopped")


def build_parser():
    parser = argparse.ArgumentParser(description="Cross-platform wallpaper scheduler")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--daemon", action="store_true", help="run continuously")
    group.add_argument("--apply-now", action="store_true", help="apply current slot once")
    group.add_argument("--set", metavar="IMAGE", help="set a specific image now")
    group.add_argument("--status", action="store_true", help="show active slot + current wallpaper")
    group.add_argument("--list", action="store_true", help="show schedule")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    cfg = load_config()

    if args.daemon:
        run_daemon(cfg)
    elif args.apply_now:
        os._exit(0 if apply_current(cfg, force=True) else 1)
    elif args.set:
        target = Path(os.path.expanduser(args.set))
        ok = set_wallpaper(target)
        log(f"set mechanism: {'OK' if ok else 'FAILED'} -> {target}")
        os._exit(0 if ok else 1)
    elif args.status:
        print_status(cfg)
    elif args.list:
        print_schedule(cfg)
    else:
        build_parser().print_help()


if __name__ == "__main__":
    main()


# --------------------------------------------------------------------------- #
# Design notes:
# - Shared logic for config/schedule/state lives above.
# - Backends for macOS and Windows are isolated in the platform-specific section.
# - This keeps one code path for scheduling while allowing OS-specific wallpaper
#   switching. That is the cross-platform abstraction pattern.
# --------------------------------------------------------------------------- #

# Wallpaper Agent

This repository holds a cross-platform wallpaper agent that uses the same scheduling logic across operating systems while delegating actual wallpaper changes to platform-specific backends.

## What this repo is designed to do

- Run a schedule of wallpapers throughout the day
- Support macOS native wallpaper switching
- Support Windows static wallpaper switching
- Support Windows live/video wallpaper switching when Lively Wallpaper is installed
- Keep the schedule and config logic in one shared implementation

## Why this is the cross-platform abstraction approach

Instead of maintaining two separate scripts (`wallpaper_agent.py` and `wallpaper_agent_windows.py`), the code is structured around a single scheduler with OS-specific execution functions:

- `set_wallpaper()` chooses the correct backend based on `platform.system()`
- Shared config/state logic stays in one place
- macOS and Windows-specific behavior stays isolated behind the backend layer

## Files

- `wallpaper_agent.py` — main scheduling logic and OS dispatch
- `wallpapers.json` — sample metadata for wallpaper entries

## macOS notes

The original macOS script supported native AppleScript wallpaper switching and dynamic aerial support. This repo intentionally keeps the abstraction clean and leaves the advanced native aerial implementation in the macOS backend if you want to expand it later.

## Windows notes

On Windows, the script tries to use Lively Wallpaper when a video/live wallpaper is requested. If Lively is not installed, it falls back to the standard Windows wallpaper API for static images.

## Example usage

```bash
python3 wallpaper_agent.py --list
python3 wallpaper_agent.py --status
python3 wallpaper_agent.py --apply-now
python3 wallpaper_agent.py --set "C:/Users/you/Pictures/wallpaper.jpg"
```

## Recommended next step

If you want the agent to fetch wallpaper metadata from GitHub, the clean pattern is:

- keep this repo as the codebase
- store schedule metadata in `wallpapers.json`
- fetch that JSON from GitHub at startup or on a timed refresh
- use the local machine to actually apply the wallpaper

This keeps GitHub as a config source instead of a real-time database.

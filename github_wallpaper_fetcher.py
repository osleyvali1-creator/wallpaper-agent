#!/usr/bin/env python3
"""GitHub wallpaper metadata fetcher for the wallpaper agent.

This module is intentionally lightweight and only fetches config metadata from
GitHub; it does not store or distribute the wallpaper media itself.
"""
import json
import os
import time
from pathlib import Path
from urllib import request, error

REPO_OWNER = "osleyvali1-creator"
REPO_NAME = "wallpaper-agent"
RAW_URL = (
    f"https://raw.githubusercontent.com/{REPO_OWNER}/{REPO_NAME}/main/wallpapers.json"
)
CACHE_PATH = Path(__file__).resolve().parent / ".wallpapers_cache.json"


def fetch_wallpapers_from_github(url=RAW_URL, timeout=20):
    """Fetch the wallpaper metadata JSON from GitHub.

    Returns a parsed dict or raises an exception if the file cannot be fetched.
    """
    try:
        with request.urlopen(url, timeout=timeout) as resp:
            payload = resp.read().decode("utf-8")
        data = json.loads(payload)
        if not isinstance(data, dict) or "wallpapers" not in data:
            raise ValueError("wallpapers.json is missing the 'wallpapers' key")
        return data
    except Exception:
        raise


def load_cached_wallpapers():
    if not CACHE_PATH.exists():
        return None
    try:
        return json.loads(CACHE_PATH.read_text())
    except Exception:
        return None


def save_cached_wallpapers(data):
    CACHE_PATH.write_text(json.dumps(data, indent=2) + "\n")


def refresh_wallpaper_data():
    """Refresh the wallpaper metadata from GitHub and cache the result."""
    data = fetch_wallpapers_from_github()
    save_cached_wallpapers(data)
    return data


def get_wallpaper_data(force_refresh=False):
    """Return wallpaper metadata from GitHub, falling back to cache if needed."""
    if force_refresh:
        return refresh_wallpaper_data()

    try:
        return fetch_wallpapers_from_github()
    except Exception:
        cached = load_cached_wallpapers()
        if cached is not None:
            return cached
        raise

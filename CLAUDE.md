# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Two macOS menu bar apps built with `rumps` (Python) and packaged as standalone `.app` bundles via PyInstaller. Both live in the same repo and share a similar build/deploy pattern.

| App | Source | Spec | What it does |
|-----|--------|------|--------------|
| Network Widget | `network_widget.py` | `network_widget.spec` | Ping, download/upload speed in menu bar |
| VPN Widget | `vpn_widget.py` | `vpn_widget.spec` | Shows active VPN interface (utun*) via `scutil` |

## Build

Always run from `/Users/adamz/network-widget/`:

```bash
# Build one app
pyinstaller -y network_widget.spec
pyinstaller -y vpn_widget.spec

# Full clean build (required when source changes aren't picked up)
rm -rf build dist
pyinstaller -y network_widget.spec
pyinstaller -y vpn_widget.spec
```

**Important:** Always `rm -rf build dist` before rebuilding if previous deploys showed stale behaviour. PyInstaller caches bytecode and the bundle can silently run old code even after source edits.

## Deploy

```bash
# Remove old version first (one at a time, never batched rm)
rm -rf "/Applications/Network Widget 1.1.app"
cp -r "dist/Network Widget 1.1.app" "/Applications/"

rm -rf "/Applications/VPN Widget 1.1.app"
cp -r "dist/VPN Widget 1.1.app" "/Applications/"

open "/Applications/Network Widget 1.1.app"
open "/Applications/VPN Widget 1.1.app"
```

**Never** use `rm -rf` on multiple `/Applications/` paths in a single chained command — it has caused unintended deletion of other apps.

## Versioning

Both apps use a `VERSION` string in two places — keep them in sync when bumping:

- `network_widget.py` → `VERSION = "X.X"`
- `network_widget.spec` → `VERSION = "X.X"`
- `vpn_widget.py` → `VERSION = "X.X"`
- `vpn_widget.spec` → `VERSION = "X.X"`

The spec derives the app bundle name as `f"Network Widget {VERSION}"`, so a version bump automatically produces a new uniquely-named `.app`.

## Architecture

### Threading model (both widgets)

Background threads **only write plain Python attributes**. The main-thread `@rumps.timer(1)` (`ui_tick`) reads those attributes and updates all UI. A `_dirty` flag signals when background data is ready to render. This avoids PyObjC thread-safety issues.

```
Background thread  →  writes self.ping_ms / self.vpn_connections / etc.
                   →  sets self._dirty = True
Main thread timer  →  checks _dirty, updates self.title and menu item .title strings
```

### Menu bar title

Both widgets set `self.title = "..."` with emoji status dots. **Do not use `NSAttributedString` or `self._nsapp.nsstatusitem`** — these APIs are not reliably accessible inside PyInstaller bundles and cause silent failures showing only the initial `⏳`.

Ping/status colours use plain emoji: `🟢` `🟡` `🔴` `⚪` `⚫`

### Network Widget specifics

- **Ping:** `/sbin/ping -c 4 -q 8.8.8.8` every 60 s, parsed from the `min/avg/max` summary line
- **Speed:** `networkQuality -c -I <iface>` where `<iface>` is the first `en*` entry from `scutil --nwi` — this bypasses the VPN tunnel and tests on the physical interface
- **History:** last 10 speed results stored in `self.speed_history`; submenu rebuilt on main thread when `self._history_dirty` is set

### VPN Widget specifics

- Data source: `scutil --nc list` + `scutil --nc status <name>` per connected VPN
- Menu uses **fixed pre-allocated `rumps.MenuItem` instances** whose `.title` is updated in place — dynamic add/remove from the main menu is unreliable in rumps and should be avoided
- Refreshes every 30 s; "Refresh" button forces immediate next tick

## Dependencies

```bash
pip install rumps pyinstaller
```

`networkQuality` and `scutil` are macOS system binaries — no install needed.
`setup.py` is a legacy py2app file and is not used; PyInstaller specs are the active build system.

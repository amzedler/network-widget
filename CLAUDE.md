# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

macOS menu bar apps for network and VPN monitoring.

| App | Source | Language | What it does |
|-----|--------|----------|--------------|
| Network Widget | `NetworkWidget.swift` | Swift (native) | Ping, download/upload speed with charts in menu bar |
| VPN Widget | `vpn_widget.py` | Python (rumps) | Shows active VPN interface (utun*) via `scutil` |

## Build

### Network Widget (Swift)

```bash
swiftc -O -o NetworkWidget NetworkWidget.swift -framework Cocoa
```

### VPN Widget (Python)

```bash
pyinstaller -y vpn_widget.spec
```

**Important:** Always `rm -rf build dist` before rebuilding the VPN widget if previous deploys showed stale behaviour.

## Bundle & Deploy

### Network Widget

```bash
# Build .app bundle
mkdir -p dist/NetworkWidget.app/Contents/MacOS
cp NetworkWidget dist/NetworkWidget.app/Contents/MacOS/
# Info.plist is already in dist/NetworkWidget.app/Contents/

# Deploy
rm -rf "/Applications/NetworkWidget.app"
cp -r "dist/NetworkWidget.app" "/Applications/"
open "/Applications/NetworkWidget.app"
```

### VPN Widget

```bash
rm -rf "/Applications/VPN Widget 1.1.app"
cp -r "dist/VPN Widget 1.1.app" "/Applications/"
open "/Applications/VPN Widget 1.1.app"
```

**Never** use `rm -rf` on multiple `/Applications/` paths in a single chained command — it has caused unintended deletion of other apps.

## Architecture

### Network Widget (Swift, native Cocoa)

- Single-file Swift app using `NSStatusItem` + `NSMenu` with `NSMenuDelegate`
- Menu bar: colored `●` dot + ping value using `NSAttributedString` (monospaced digits, 11pt)
- `menuWillOpen` builds the entire menu from cached data — no blocking calls on click
- Background work via `DispatchQueue.global(qos: .utility)`, results dispatched back to main thread
- **Ping:** `/sbin/ping -c 4 -q 8.8.8.8`, configurable interval (1s–60s) via Ping Frequency submenu
- **Speed:** `networkQuality -c -I <iface>` where `<iface>` is the first `en*` from `scutil --nwi` (bypasses VPN)
- **Charts:** Core Graphics line charts (`PingChartView`, `SpeedChartView`) with gradient fills, threshold lines, auto-scaling Y axis, 2-hour time window
- **History:** up to 240 ping samples + 30 speed tests; speed history shown as stat rows in dropdown

### VPN Widget (Python, rumps)

- Data source: `scutil --nc list` + `scutil --nc status <name>` per connected VPN
- Menu uses **fixed pre-allocated `rumps.MenuItem` instances** whose `.title` is updated in place
- Refreshes every 30s; "Refresh" button forces immediate next tick

## Dependencies

### Network Widget
- Xcode Command Line Tools (`swiftc`)
- No external dependencies — Cocoa framework only
- `networkQuality` and `scutil` are macOS system binaries

### VPN Widget
```bash
pip install rumps pyinstaller
```

## Legacy Files

- `network_widget.py` / `network_widget.spec` — old Python/rumps version, superseded by `NetworkWidget.swift`
- `setup.py` — legacy py2app file, not used

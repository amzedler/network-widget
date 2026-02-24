#!/usr/bin/env python3
"""
Network Toolbar Widget
- Ping: tested every 60 seconds (8.8.8.8)
- Speed: tested every 60 minutes
"""

import rumps
import subprocess
import threading
import time
import datetime
import json
import re

VERSION = "1.1"
MAX_HISTORY = 10

PING_INTERVAL = 60       # seconds
SPEED_INTERVAL = 600     # seconds (10 minutes)
PING_HOST = "8.8.8.8"
PING_COUNT = 4


def measure_ping():
    """Returns average ping in ms, or None on failure."""
    try:
        result = subprocess.run(
            ["/sbin/ping", "-c", str(PING_COUNT), "-q", PING_HOST],
            capture_output=True, text=True, timeout=15
        )
        for line in result.stdout.splitlines():
            # macOS ping summary: "round-trip min/avg/max/stddev = 4.123/5.456/6.789/0.123 ms"
            if "avg" in line or "min/avg" in line:
                parts = line.split("=")[-1].strip().split("/")
                avg_ms = float(parts[1])
                return avg_ms
    except Exception:
        pass
    return None


# Ping thresholds for color indicator (ms)
PING_GOOD = 50
PING_WARN = 100


def _fmt_speed(mbps):
    """Format Mbps compactly: ≥1000 → single decimal Gbps, else integer Mbps."""
    if mbps is None:
        return "…"
    if mbps >= 1000:
        return f"{mbps / 1000:.1f}G"
    return f"{mbps:.0f}M"


def _physical_interface():
    """Return the first non-VPN en* interface from scutil --nwi, or None."""
    try:
        result = subprocess.run(["scutil", "--nwi"], capture_output=True, text=True, timeout=5)
        for line in result.stdout.splitlines():
            m = re.match(r'\s+(en\d+)\s*:', line)
            if m:
                return m.group(1)
    except Exception:
        pass
    return None


def measure_speed():
    """Returns (download_mbps, upload_mbps, server_str) or (None, None, None) on failure."""
    try:
        iface = _physical_interface()
        cmd = ["/usr/bin/networkQuality", "-c"]
        if iface:
            cmd += ["-I", iface]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
        data = json.loads(result.stdout)
        dl = data["dl_throughput"] / 1_000_000   # bits/s → Mbps
        ul = data["ul_throughput"] / 1_000_000
        label = iface or data.get("interface_name", "?")
        return dl, ul, f"Apple CDN ({label})"
    except Exception:
        pass
    return None, None, None


class NetworkWidget(rumps.App):
    def __init__(self):
        super().__init__("⏳", quit_button=None)

        # Data (written by background threads, read by main-thread timer)
        self.ping_ms = None
        self.dl_mbps = None
        self.ul_mbps = None
        self.speed_running = False
        self.ping_label   = "Ping: —"
        self.dl_label     = "Download: —"
        self.ul_label     = "Upload: —"
        self.server_label = "Server: —"

        # Speed test history (written by background thread, rebuilt on main thread)
        self.speed_history = []   # list of dicts: {time, dl, ul, server}
        self._history_dirty = False

        # Menu items
        self.ping_item   = rumps.MenuItem("Ping: —")
        self.dl_item     = rumps.MenuItem("Download: —")
        self.ul_item     = rumps.MenuItem("Upload: —")
        self.server_item = rumps.MenuItem("Server: —")
        self.next_speed  = rumps.MenuItem("Next speed test: —")
        self.run_now_item = rumps.MenuItem("Run Speed Test Now", callback=self._on_run_now)

        self.history_menu = rumps.MenuItem("Speed Test History")
        self.history_menu.add(rumps.MenuItem("No history yet"))

        self.menu = [
            self.ping_item,
            self.dl_item,
            self.ul_item,
            self.server_item,
            None,
            self.history_menu,
            None,
            self.next_speed,
            self.run_now_item,
            None,
            rumps.MenuItem("Quit", callback=rumps.quit_application),
        ]

        self._speed_next_time = 0  # triggers immediately on first UI tick
        self._next_ping_time  = 0  # triggers immediately on first UI tick

    # ------------------------------------------------------------------
    # Main-thread timer — safe to update all UI here
    # ------------------------------------------------------------------
    @rumps.timer(1)
    def ui_tick(self, _):
        now = time.time()

        # Kick off a ping in the background if it's time
        if now >= self._next_ping_time:
            self._next_ping_time = now + PING_INTERVAL
            threading.Thread(target=self._run_ping, daemon=True).start()

        # Kick off a speed test in the background if it's time
        if now >= self._speed_next_time and not self.speed_running:
            self.speed_running = True
            self._speed_next_time = now + SPEED_INTERVAL
            threading.Thread(target=self._run_speed, daemon=True).start()

        # Update title bar
        if self.ping_ms is None:       dot = "⚪"
        elif self.ping_ms < PING_GOOD: dot = "🟢"
        elif self.ping_ms < PING_WARN: dot = "🟡"
        else:                          dot = "🔴"
        self.title = f"{dot} ↓{_fmt_speed(self.dl_mbps)} ↑{_fmt_speed(self.ul_mbps)}"

        # Update menu item labels (written by background threads)
        self.ping_item.title   = self.ping_label
        self.dl_item.title     = self.dl_label
        self.ul_item.title     = self.ul_label
        self.server_item.title = self.server_label

        # Rebuild history submenu on main thread when new data arrives
        if self._history_dirty:
            self._history_dirty = False
            self._rebuild_history_menu()

        # Countdown / run-now state
        if self.speed_running:
            self.next_speed.title   = "Running speed test…"
            self.run_now_item.title = "Speed Test Running…"
            self.run_now_item._menuitem.setEnabled_(False)
        else:
            remaining = max(0, int(self._speed_next_time - now))
            mins, secs = divmod(remaining, 60)
            self.next_speed.title   = f"Next speed test in: {mins}m {secs:02d}s"
            self.run_now_item.title = "Run Speed Test Now"
            self.run_now_item._menuitem.setEnabled_(True)

    # ------------------------------------------------------------------
    # Background workers — only write to plain Python attributes
    # ------------------------------------------------------------------
    def _run_ping(self):
        ping = measure_ping()
        self.ping_ms = ping
        if ping is not None:
            self.ping_label = f"Ping: {ping:.1f} ms  ({PING_HOST})"
        else:
            self.ping_label = "Ping: error"

    def _run_speed(self):
        dl, ul, server = measure_speed()
        self.dl_mbps = dl
        self.ul_mbps = ul
        entry = {"time": datetime.datetime.now(), "dl": dl, "ul": ul, "server": server}
        if dl is not None:
            self.dl_label     = f"Download: {dl:.1f} Mbps"
            self.ul_label     = f"Upload:   {ul:.1f} Mbps"
            self.server_label = f"Server: {server}"
        else:
            self.dl_label     = "Download: error"
            self.ul_label     = "Upload:   error"
            self.server_label = "Server: error"
        self.speed_history.append(entry)
        if len(self.speed_history) > MAX_HISTORY:
            self.speed_history = self.speed_history[-MAX_HISTORY:]
        self._history_dirty = True
        self.speed_running = False

    def _rebuild_history_menu(self):
        """Rebuild history submenu — must be called from the main thread."""
        for key in list(self.history_menu.keys()):
            del self.history_menu[key]
        if not self.speed_history:
            self.history_menu.add(rumps.MenuItem("No history yet"))
            return
        self.history_menu.title = f"Speed Test History ({len(self.speed_history)})"
        for entry in reversed(self.speed_history):
            ts = entry["time"].strftime("%m/%d %H:%M")
            if entry["dl"] is not None:
                label = f"{ts}  ↓{entry['dl']:.0f}  ↑{entry['ul']:.0f} Mbps"
            else:
                label = f"{ts}  error"
            self.history_menu.add(rumps.MenuItem(label))

    def _on_run_now(self, _):
        if not self.speed_running:
            self.speed_running = True
            self._speed_next_time = time.time() + SPEED_INTERVAL
            threading.Thread(target=self._run_speed, daemon=True).start()


if __name__ == "__main__":
    NetworkWidget().run()

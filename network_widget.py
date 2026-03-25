#!/usr/bin/env python3
"""
Network Toolbar Widget
- Ping: tested every 60 seconds (8.8.8.8)
- Speed: tested every 10 minutes
"""

import rumps
import subprocess
import threading
import time
import datetime
import json
import re

VERSION = "1.2"
MAX_SPEED_HISTORY = 30   # ~5 hours at 10min intervals
MAX_PING_HISTORY = 120   # ~2 hours at 60s intervals

PING_INTERVAL = 60       # seconds
SPEED_INTERVAL = 600     # seconds (10 minutes)
PING_HOST = "8.8.8.8"
PING_COUNT = 4

PING_GOOD = 50   # ms
PING_WARN = 100


def measure_ping():
    """Returns average ping in ms, or None on failure."""
    try:
        result = subprocess.run(
            ["/sbin/ping", "-c", str(PING_COUNT), "-q", PING_HOST],
            capture_output=True, text=True, timeout=15
        )
        for line in result.stdout.splitlines():
            if "avg" in line or "min/avg" in line:
                parts = line.split("=")[-1].strip().split("/")
                return float(parts[1])
    except Exception:
        pass
    return None


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
        dl = data["dl_throughput"] / 1_000_000
        ul = data["ul_throughput"] / 1_000_000
        label = iface or data.get("interface_name", "?")
        return dl, ul, f"Apple CDN ({label})"
    except Exception:
        pass
    return None, None, None


def _fmt_speed(mbps):
    if mbps is None:
        return "–"
    if mbps >= 1000:
        return f"{mbps / 1000:.1f} Gbps"
    return f"{mbps:.0f} Mbps"


def _show_graph(ping_history, speed_history):
    """Open a matplotlib window with ping and speed graphs."""
    threading.Thread(target=_render_graph, args=(list(ping_history), list(speed_history)), daemon=True).start()


def _render_graph(ping_history, speed_history):
    import matplotlib
    matplotlib.use("TkAgg")
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates

    fig, axes = plt.subplots(2, 1, figsize=(7, 5), sharex=True,
                             gridspec_kw={"height_ratios": [1, 1], "hspace": 0.15})
    fig.patch.set_facecolor("#1e1e1e")
    for ax in axes:
        ax.set_facecolor("#1e1e1e")
        ax.tick_params(colors="#aaa", labelsize=9)
        for spine in ax.spines.values():
            spine.set_color("#333")
        ax.grid(True, color="#333", linewidth=0.5, alpha=0.7)

    # --- Ping chart ---
    ax_ping = axes[0]
    if ping_history:
        times = [e["time"] for e in ping_history]
        pings = [e["ms"] for e in ping_history]
        ax_ping.plot(times, pings, color="#4fc3f7", linewidth=1.5, marker=".", markersize=3)
        ax_ping.axhline(y=PING_GOOD, color="#66bb6a", linewidth=0.8, linestyle="--", alpha=0.6)
        ax_ping.axhline(y=PING_WARN, color="#ffa726", linewidth=0.8, linestyle="--", alpha=0.6)
        ax_ping.fill_between(times, pings, alpha=0.1, color="#4fc3f7")
    ax_ping.set_ylabel("Ping (ms)", color="#aaa", fontsize=10)
    ax_ping.set_title("Network Performance", color="#ddd", fontsize=12, fontweight="bold", pad=10)

    # --- Speed chart ---
    ax_speed = axes[1]
    if speed_history:
        times = [e["time"] for e in speed_history if e["dl"] is not None]
        dl = [e["dl"] for e in speed_history if e["dl"] is not None]
        ul = [e["ul"] for e in speed_history if e["dl"] is not None]
        if times:
            ax_speed.plot(times, dl, color="#66bb6a", linewidth=1.5, marker="o", markersize=4, label="Download")
            ax_speed.plot(times, ul, color="#ffa726", linewidth=1.5, marker="s", markersize=4, label="Upload")
            ax_speed.fill_between(times, dl, alpha=0.1, color="#66bb6a")
            ax_speed.fill_between(times, ul, alpha=0.1, color="#ffa726")
            ax_speed.legend(fontsize=9, facecolor="#1e1e1e", edgecolor="#333", labelcolor="#aaa", loc="upper left")
    ax_speed.set_ylabel("Speed (Mbps)", color="#aaa", fontsize=10)
    ax_speed.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    ax_speed.set_xlabel("Time", color="#aaa", fontsize=10)

    plt.tight_layout()
    plt.show()


class NetworkWidget(rumps.App):
    def __init__(self):
        super().__init__("⏳", quit_button=None)

        # Data (written by background threads, read by main-thread timer)
        self.ping_ms = None
        self.dl_mbps = None
        self.ul_mbps = None
        self.speed_running = False

        # History for graphs
        self.ping_history = []    # [{time, ms}]
        self.speed_history = []   # [{time, dl, ul, server}]
        self._history_dirty = False

        # Menu items
        self.ping_item    = rumps.MenuItem("Ping: –")
        self.dl_item      = rumps.MenuItem("Download: –")
        self.ul_item      = rumps.MenuItem("Upload: –")
        self.server_item  = rumps.MenuItem("Server: –")
        self.graph_item   = rumps.MenuItem("Show Graph", callback=self._on_show_graph)
        self.next_speed   = rumps.MenuItem("Next speed test: –")
        self.run_now_item = rumps.MenuItem("Run Speed Test Now", callback=self._on_run_now)

        self.history_menu = rumps.MenuItem("Speed Test History")
        self.history_menu.add(rumps.MenuItem("No history yet"))

        self.menu = [
            self.ping_item,
            self.dl_item,
            self.ul_item,
            self.server_item,
            None,
            self.graph_item,
            self.history_menu,
            None,
            self.next_speed,
            self.run_now_item,
            None,
            rumps.MenuItem("Quit", callback=rumps.quit_application),
        ]

        self._speed_next_time = 0
        self._next_ping_time  = 0

    # ------------------------------------------------------------------
    # Main-thread timer
    # ------------------------------------------------------------------
    @rumps.timer(1)
    def ui_tick(self, _):
        now = time.time()

        if now >= self._next_ping_time:
            self._next_ping_time = now + PING_INTERVAL
            threading.Thread(target=self._run_ping, daemon=True).start()

        if now >= self._speed_next_time and not self.speed_running:
            self.speed_running = True
            self._speed_next_time = now + SPEED_INTERVAL
            threading.Thread(target=self._run_speed, daemon=True).start()

        # Compact title: ● XXms  (mimics MemoryBar style)
        if self.ping_ms is None:       dot = "⚪"
        elif self.ping_ms < PING_GOOD: dot = "🟢"
        elif self.ping_ms < PING_WARN: dot = "🟡"
        else:                          dot = "🔴"

        if self.ping_ms is not None:
            self.title = f"{dot} {self.ping_ms:.0f}ms"
        else:
            self.title = f"{dot} –"

        # Menu labels
        if self.ping_ms is not None:
            self.ping_item.title = f"Ping: {self.ping_ms:.1f} ms  ({PING_HOST})"
        self.dl_item.title     = f"Download: {_fmt_speed(self.dl_mbps)}"
        self.ul_item.title     = f"Upload: {_fmt_speed(self.ul_mbps)}"

        if self._history_dirty:
            self._history_dirty = False
            self._rebuild_history_menu()

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
    # Background workers
    # ------------------------------------------------------------------
    def _run_ping(self):
        ping = measure_ping()
        self.ping_ms = ping
        if ping is not None:
            self.ping_history.append({"time": datetime.datetime.now(), "ms": ping})
            if len(self.ping_history) > MAX_PING_HISTORY:
                self.ping_history = self.ping_history[-MAX_PING_HISTORY:]

    def _run_speed(self):
        dl, ul, server = measure_speed()
        self.dl_mbps = dl
        self.ul_mbps = ul
        self.speed_history.append({
            "time": datetime.datetime.now(), "dl": dl, "ul": ul, "server": server
        })
        if dl is not None:
            self.server_item.title = f"Server: {server}"
        else:
            self.server_item.title = "Server: error"
        if len(self.speed_history) > MAX_SPEED_HISTORY:
            self.speed_history = self.speed_history[-MAX_SPEED_HISTORY:]
        self._history_dirty = True
        self.speed_running = False

    def _rebuild_history_menu(self):
        for key in list(self.history_menu.keys()):
            del self.history_menu[key]
        valid = [e for e in self.speed_history if e["dl"] is not None]
        if not valid:
            self.history_menu.add(rumps.MenuItem("No history yet"))
            return
        self.history_menu.title = f"Speed Test History ({len(valid)})"
        for entry in reversed(valid):
            ts = entry["time"].strftime("%H:%M")
            self.history_menu.add(rumps.MenuItem(
                f"{ts}  ↓{entry['dl']:.0f}  ↑{entry['ul']:.0f} Mbps"
            ))

    def _on_run_now(self, _):
        if not self.speed_running:
            self.speed_running = True
            self._speed_next_time = time.time() + SPEED_INTERVAL
            threading.Thread(target=self._run_speed, daemon=True).start()

    def _on_show_graph(self, _):
        _show_graph(self.ping_history, self.speed_history)


if __name__ == "__main__":
    NetworkWidget().run()

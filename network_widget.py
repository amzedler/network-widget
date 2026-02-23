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
import speedtest as speedtest_lib

PING_INTERVAL = 60       # seconds
SPEED_INTERVAL = 3600    # seconds (1 hour)
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


def measure_speed():
    """Returns (download_mbps, upload_mbps) or (None, None) on failure."""
    try:
        st = speedtest_lib.Speedtest(secure=True)
        st.get_best_server()
        st.download(threads=4)
        st.upload(threads=4)
        results = st.results.dict()
        dl = results["download"] / 1_000_000  # bits → Mbps
        ul = results["upload"] / 1_000_000
        return dl, ul
    except Exception:
        return None, None


class NetworkWidget(rumps.App):
    def __init__(self):
        super().__init__("⏳", quit_button=None)

        # Data (written by background threads, read by main-thread timer)
        self.ping_ms = None
        self.dl_mbps = None
        self.ul_mbps = None
        self.speed_running = False
        self.ping_label = "Ping: —"
        self.dl_label   = "Download: —"
        self.ul_label   = "Upload: —"

        # Menu items
        self.ping_item  = rumps.MenuItem("Ping: —")
        self.dl_item    = rumps.MenuItem("Download: —")
        self.ul_item    = rumps.MenuItem("Upload: —")
        self.next_speed = rumps.MenuItem("Next speed test: —")
        self.menu = [
            self.ping_item,
            self.dl_item,
            self.ul_item,
            None,
            self.next_speed,
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
        ping_str = f"{self.ping_ms:.0f}ms" if self.ping_ms is not None else "⏳"
        dl_str   = f"↓{self.dl_mbps:.0f}"  if self.dl_mbps  is not None else "↓?"
        ul_str   = f"↑{self.ul_mbps:.0f}"  if self.ul_mbps  is not None else "↑?"
        self.title = f"{ping_str}  {dl_str}/{ul_str} Mbps"

        # Update menu item labels (written by background threads)
        self.ping_item.title = self.ping_label
        self.dl_item.title   = self.dl_label
        self.ul_item.title   = self.ul_label

        # Countdown to next speed test
        if self.speed_running:
            self.next_speed.title = "Running speed test…"
        else:
            remaining = max(0, int(self._speed_next_time - now))
            mins, secs = divmod(remaining, 60)
            self.next_speed.title = f"Next speed test in: {mins}m {secs:02d}s"

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
        dl, ul = measure_speed()
        self.dl_mbps = dl
        self.ul_mbps = ul
        if dl is not None:
            self.dl_label = f"Download: {dl:.1f} Mbps"
            self.ul_label = f"Upload:   {ul:.1f} Mbps"
        else:
            self.dl_label = "Download: error"
            self.ul_label = "Upload:   error"
        self.speed_running = False


if __name__ == "__main__":
    NetworkWidget().run()

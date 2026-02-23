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
            ["ping", "-c", str(PING_COUNT), "-q", PING_HOST],
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
        super().__init__("⏳ …", quit_button=None)

        self.ping_ms = None
        self.dl_mbps = None
        self.ul_mbps = None
        self.speed_running = False

        # Menu items (read-only labels + separator + quit)
        self.ping_item  = rumps.MenuItem("Ping: —")
        self.dl_item    = rumps.MenuItem("Download: —")
        self.ul_item    = rumps.MenuItem("Upload: —")
        self.next_speed = rumps.MenuItem("Next speed test: —")
        self.menu = [
            self.ping_item,
            self.dl_item,
            self.ul_item,
            None,  # separator
            self.next_speed,
            None,
            rumps.MenuItem("Quit", callback=rumps.quit_application),
        ]

        self._speed_next_time = 0   # run immediately on first tick
        self._speed_last_run  = None

        # Start background worker
        t = threading.Thread(target=self._worker, daemon=True)
        t.start()

    # ------------------------------------------------------------------
    # Background worker — runs forever, fires ping + speed on schedule
    # ------------------------------------------------------------------
    def _worker(self):
        while True:
            # --- Ping ---
            ping = measure_ping()
            self.ping_ms = ping
            self._refresh_title()

            if ping is not None:
                self.ping_item.title = f"Ping: {ping:.1f} ms  ({PING_HOST})"
            else:
                self.ping_item.title = "Ping: error"

            # --- Speed (once per hour) ---
            now = time.time()
            if now >= self._speed_next_time and not self.speed_running:
                self.speed_running = True
                self.next_speed.title = "Running speed test…"
                st = threading.Thread(target=self._run_speed, daemon=True)
                st.start()

            # Update "next speed test" countdown
            if not self.speed_running:
                remaining = max(0, int(self._speed_next_time - time.time()))
                mins, secs = divmod(remaining, 60)
                self.next_speed.title = f"Next speed test in: {mins}m {secs:02d}s"

            time.sleep(PING_INTERVAL)

    def _run_speed(self):
        dl, ul = measure_speed()
        self.dl_mbps = dl
        self.ul_mbps = ul
        self._speed_last_run = time.time()
        self._speed_next_time = time.time() + SPEED_INTERVAL
        self.speed_running = False
        self._refresh_title()

        if dl is not None:
            self.dl_item.title = f"Download: {dl:.1f} Mbps"
            self.ul_item.title = f"Upload:   {ul:.1f} Mbps"
        else:
            self.dl_item.title = "Download: error"
            self.ul_item.title = "Upload:   error"

    # ------------------------------------------------------------------
    # Title bar text
    # ------------------------------------------------------------------
    def _refresh_title(self):
        ping_str  = f"{self.ping_ms:.0f}ms" if self.ping_ms is not None else "?ms"
        dl_str    = f"↓{self.dl_mbps:.0f}" if self.dl_mbps is not None else "↓?"
        ul_str    = f"↑{self.ul_mbps:.0f}" if self.ul_mbps is not None else "↑?"
        self.title = f"{ping_str}  {dl_str}/{ul_str} Mbps"


if __name__ == "__main__":
    NetworkWidget().run()

#!/usr/bin/env python3
"""
VPN Toolbar Widget
- Detects active VPN connections via scutil
- Shows utun interface and status in menu bar
- Refreshes every 30 seconds
"""

import rumps
import subprocess
import threading
import time
import re
from datetime import datetime

VERSION = "1.1"
REFRESH_INTERVAL = 30  # seconds


def get_vpn_connections():
    """Returns list of dicts: {name, status, interface, ip, dns, connected_since, is_primary}."""
    connections = []
    try:
        result = subprocess.run(
            ["scutil", "--nc", "list"],
            capture_output=True, text=True, timeout=5
        )
        for line in result.stdout.splitlines():
            status_m = re.search(r'\((Connected|Disconnected|Connecting|Disconnecting)\)', line)
            name_m   = re.search(r'"([^"]+)"', line)
            if not (status_m and name_m):
                continue
            status = status_m.group(1)
            name   = name_m.group(1)
            vpn = {
                "name": name, "status": status,
                "interface": None, "ip": None, "dns": None,
                "connected_since": None, "is_primary": False,
            }
            if status == "Connected":
                detail = subprocess.run(
                    ["scutil", "--nc", "status", name],
                    capture_output=True, text=True, timeout=5
                )
                t = detail.stdout
                iface_m   = re.search(r'InterfaceName\s*:\s*(\S+)', t)
                ip_m      = re.search(r'Addresses\s*:.*?0\s*:\s*([\d.]+)', t, re.DOTALL)
                dns_m     = re.search(r'DNSServers\s*:.*?0\s*:\s*([\d.]+)', t, re.DOTALL)
                primary_m = re.search(r'IsPrimaryInterface\s*:\s*(\d+)', t)
                time_m    = re.search(r'LastStatusChangeTime\s*:\s*(.+)', t)
                if iface_m:   vpn["interface"]      = iface_m.group(1)
                if ip_m:      vpn["ip"]              = ip_m.group(1)
                if dns_m:     vpn["dns"]             = dns_m.group(1)
                if primary_m: vpn["is_primary"]      = primary_m.group(1) == "1"
                if time_m:
                    try:
                        vpn["connected_since"] = datetime.strptime(
                            time_m.group(1).strip(), "%m/%d/%Y %H:%M:%S"
                        )
                    except ValueError:
                        pass
            connections.append(vpn)
    except Exception:
        pass
    return connections


class VpnWidget(rumps.App):
    def __init__(self):
        super().__init__("⏳", quit_button=None)

        self.vpn_connections = []
        self._dirty = False

        # Fixed menu items — titles updated in place, no add/remove
        self.status_item  = rumps.MenuItem("Detecting…")
        self.iface_item   = rumps.MenuItem("")
        self.ip_item      = rumps.MenuItem("")
        self.dns_item     = rumps.MenuItem("")
        self.since_item   = rumps.MenuItem("")
        self.refresh_item = rumps.MenuItem("Refresh", callback=self._on_refresh)

        self.menu = [
            self.status_item,
            self.iface_item,
            self.ip_item,
            self.dns_item,
            self.since_item,
            None,
            self.refresh_item,
            None,
            rumps.MenuItem("Quit", callback=rumps.quit_application),
        ]

        self._next_refresh = 0  # fire immediately on first tick

    @rumps.timer(1)
    def ui_tick(self, _):
        now = time.time()
        if now >= self._next_refresh:
            self._next_refresh = now + REFRESH_INTERVAL
            threading.Thread(target=self._run_refresh, daemon=True).start()

        if self._dirty:
            self._dirty = False
            self._update_ui()

    def _run_refresh(self):
        self.vpn_connections = get_vpn_connections()
        self._dirty = True

    def _update_ui(self):
        connected = [v for v in self.vpn_connections if v["status"] == "Connected"]
        primary   = next((v for v in connected if v["is_primary"]), connected[0] if connected else None)

        # Title bar
        if primary:
            iface = primary["interface"] or "utun?"
            extra = f" +{len(connected)-1}" if len(connected) > 1 else ""
            self.title = f"🟢 {iface}{extra}"
        elif any(v["status"] == "Connecting" for v in self.vpn_connections):
            self.title = "🟡 Connecting…"
        else:
            self.title = "⚫ No VPN"

        # Menu items
        if primary:
            iface = primary["interface"] or "utun?"
            self.status_item.title = f"{primary['name']}  —  Connected"
            self.iface_item.title  = f"  Interface:  {iface}"
            self.ip_item.title     = f"  IP:         {primary['ip'] or '—'}"
            self.dns_item.title    = f"  DNS:        {primary['dns'] or '—'}"
            if primary["connected_since"]:
                since   = primary["connected_since"].strftime("%m/%d %H:%M")
                elapsed = self._elapsed(primary["connected_since"])
                self.since_item.title = f"  Since:      {since}  ({elapsed})"
            else:
                self.since_item.title = ""
        elif self.vpn_connections:
            v = self.vpn_connections[0]
            self.status_item.title = f"{v['name']}  —  {v['status']}"
            self.iface_item.title  = ""
            self.ip_item.title     = ""
            self.dns_item.title    = ""
            self.since_item.title  = ""
        else:
            self.status_item.title = "No VPN services found"
            self.iface_item.title  = ""
            self.ip_item.title     = ""
            self.dns_item.title    = ""
            self.since_item.title  = ""

    def _elapsed(self, since):
        delta = int((datetime.now() - since).total_seconds())
        h, rem = divmod(delta, 3600)
        m = rem // 60
        return f"{h}h {m}m" if h else f"{m}m"

    def _on_refresh(self, _):
        self._next_refresh = 0


if __name__ == "__main__":
    VpnWidget().run()

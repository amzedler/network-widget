#!/usr/bin/env python3
"""
VPN Toolbar Widget
- Detects active VPN connections via scutil
- Shows utun interface and status in menu bar
- Refreshes every 30 seconds
"""

import rumps
import AppKit
import subprocess
import threading
import time
import re
from datetime import datetime

VERSION = "1.0"
REFRESH_INTERVAL = 30  # seconds


def get_vpn_connections():
    """Returns list of dicts for each VPN: {name, status, interface, ip, dns, connected_since, is_primary}."""
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
                if iface_m:   vpn["interface"]  = iface_m.group(1)
                if ip_m:      vpn["ip"]          = ip_m.group(1)
                if dns_m:     vpn["dns"]          = dns_m.group(1)
                if primary_m: vpn["is_primary"]   = primary_m.group(1) == "1"
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

        # State (written by background thread, read by main-thread timer)
        self.vpn_connections = []
        self._dirty = False
        self._last_refresh = 0

        # Static menu items
        self._vpn_items = []   # dynamically rebuilt
        self.separator1  = None
        self.refresh_item = rumps.MenuItem("Refresh", callback=self._on_refresh)

        self.menu = [
            rumps.MenuItem("Detecting…"),
            None,
            self.refresh_item,
            None,
            rumps.MenuItem("Quit", callback=rumps.quit_application),
        ]

        self._next_refresh = 0  # fire immediately on first tick

    # ------------------------------------------------------------------
    # Main-thread timer
    # ------------------------------------------------------------------
    @rumps.timer(1)
    def ui_tick(self, _):
        now = time.time()

        # Kick off a background refresh if due
        if now >= self._next_refresh:
            self._next_refresh = now + REFRESH_INTERVAL
            threading.Thread(target=self._run_refresh, daemon=True).start()

        # Rebuild UI when new data arrives
        if self._dirty:
            self._dirty = False
            self._rebuild_menu()
            self._update_title()

    # ------------------------------------------------------------------
    # Background worker
    # ------------------------------------------------------------------
    def _run_refresh(self):
        self.vpn_connections = get_vpn_connections()
        self._dirty = True

    # ------------------------------------------------------------------
    # Main-thread UI updates
    # ------------------------------------------------------------------
    def _update_title(self):
        connected = [v for v in self.vpn_connections if v["status"] == "Connected"]
        text = self._title_text(connected)
        color = self._title_color(connected)
        try:
            font = AppKit.NSFont.menuBarFontOfSize_(0)
            base_attrs = {AppKit.NSFontAttributeName: font}
            attributed = AppKit.NSMutableAttributedString.alloc().initWithString_attributes_(
                text, base_attrs
            )
            attributed.addAttribute_value_range_(
                AppKit.NSForegroundColorAttributeName,
                color,
                AppKit.NSMakeRange(0, 1),
            )
            btn = self._nsapp.nsstatusitem.button()
            if btn:
                btn.setAttributedTitle_(attributed)
        except Exception:
            self.title = text

    def _title_text(self, connected):
        if not connected:
            return "○ No VPN"
        primary = next((v for v in connected if v["is_primary"]), connected[0])
        iface = primary["interface"] or "utun?"
        if len(connected) > 1:
            return f"● {iface} +{len(connected) - 1}"
        return f"● {iface}"

    def _title_color(self, connected):
        if not connected:
            return AppKit.NSColor.grayColor()
        return AppKit.NSColor.systemGreenColor()

    def _rebuild_menu(self):
        # Clear everything except the static tail (Refresh, separator, Quit)
        for key in list(self.menu.keys()):
            item = self.menu[key]
            if hasattr(item, 'title') and item.title in ("Refresh", "Quit"):
                continue
            del self.menu[key]

        connected    = [v for v in self.vpn_connections if v["status"] == "Connected"]
        disconnected = [v for v in self.vpn_connections if v["status"] != "Connected"]

        entries = []

        if not self.vpn_connections:
            entries.append(rumps.MenuItem("No VPN services found"))
        else:
            for vpn in connected:
                iface = vpn["interface"] or "utun?"
                label = f"{vpn['name']}  ({iface})"
                parent = rumps.MenuItem(label)
                if vpn["ip"]:
                    parent.add(rumps.MenuItem(f"IP:        {vpn['ip']}"))
                if vpn["dns"]:
                    parent.add(rumps.MenuItem(f"DNS:       {vpn['dns']}"))
                if vpn["connected_since"]:
                    since = vpn["connected_since"].strftime("%m/%d %H:%M")
                    elapsed = self._elapsed(vpn["connected_since"])
                    parent.add(rumps.MenuItem(f"Connected: {since}  ({elapsed})"))
                entries.append(parent)

            if disconnected:
                entries.append(None)
                for vpn in disconnected:
                    entries.append(rumps.MenuItem(f"○ {vpn['name']}  ({vpn['status']})"))

        entries.append(None)

        # Rebuild menu preserving Refresh and Quit at the end
        new_menu = entries + [self.refresh_item, None,
                              rumps.MenuItem("Quit", callback=rumps.quit_application)]
        self.menu.clear()
        for item in new_menu:
            if item is None:
                self.menu.add(rumps.separator)
            else:
                self.menu.add(item)

    def _elapsed(self, since):
        delta = int((datetime.now() - since).total_seconds())
        h, rem = divmod(delta, 3600)
        m = rem // 60
        if h:
            return f"{h}h {m}m"
        return f"{m}m"

    def _on_refresh(self, _):
        self._next_refresh = 0  # force immediate refresh on next tick


if __name__ == "__main__":
    VpnWidget().run()

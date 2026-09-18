import http.server
import socketserver
import urllib.request
import urllib.parse
import json
import os
import sys
import socket
import concurrent.futures

import threading
import time

PORT = 7070
DIRECTORY = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(DIRECTORY, "bulb_config.json")

BULB_IS_ONLINE = False
WATCHDOG_LAST_CHECK = 0

def load_bulb_ip():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                data = json.load(f)
                return data.get("bulb_ip", "192.168.1.11")
        except Exception:
            pass
    return "192.168.1.11"

def save_bulb_ip(ip):
    global CURRENT_BULB_IP
    CURRENT_BULB_IP = ip.strip()
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump({"bulb_ip": CURRENT_BULB_IP}, f)
    except Exception:
        pass

CURRENT_BULB_IP = load_bulb_ip()

def execute_tasmota(cmd, ip=None, timeout=3.5):
    target = ip if ip else CURRENT_BULB_IP
    url = f"http://{target}/cm?cmnd={urllib.parse.quote(cmd)}"
    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Lumina/3.2',
        'Referer': f'http://{target}/'
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except Exception as e:
        return 500, json.dumps({"error": str(e), "target_ip": target}).encode()

def check_bulb_alive(ip):
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(0.3)
        res = s.connect_ex((ip, 80))
        s.close()
        if res == 0:
            status, _ = execute_tasmota("Status", ip=ip, timeout=1.0)
            return status == 200
    except Exception:
        pass
    return False

def scan_single_ip(ip):
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(0.3)
        if s.connect_ex((ip, 80)) == 0:
            s.close()
            try:
                url = f"http://{ip}/cm?cmnd=Status"
                req = urllib.request.Request(url, headers={'User-Agent': 'Lumina/3.2'})
                with urllib.request.urlopen(req, timeout=1.0) as resp:
                    raw = resp.read().decode('utf-8', errors='ignore')
                    if "Status" in raw or "Module" in raw or "FriendlyName" in raw or "Command" in raw:
                        return (ip, True, raw)
            except Exception:
                # Also check root for Tasmota minimal or standard index
                try:
                    url = f"http://{ip}/"
                    req = urllib.request.Request(url, headers={'User-Agent': 'Lumina/3.2'})
                    with urllib.request.urlopen(req, timeout=1.0) as resp:
                        raw = resp.read().decode('utf-8', errors='ignore')
                        if "Tasmota" in raw or "Smitch" in raw:
                            return (ip, True, raw)
                except Exception:
                    pass
        else:
            s.close()
    except Exception:
        pass
    return None

def auto_discover_bulb(subnet="192.168.1."):
    global BULB_IS_ONLINE
    # 1. Check current configured IP first
    if check_bulb_alive(CURRENT_BULB_IP):
        BULB_IS_ONLINE = True
        return {"found": True, "ip": CURRENT_BULB_IP, "is_ap": False, "details": "Active Bulb Confirmed"}

    # 2. Check 192.168.4.1 (Tasmota / Smitch Direct AP Mode)
    ap_res = scan_single_ip("192.168.4.1")
    if ap_res:
        save_bulb_ip("192.168.4.1")
        BULB_IS_ONLINE = True
        return {"found": True, "ip": "192.168.4.1", "is_ap": True, "details": "Smitch / Tasmota Pairing Hotspot"}

    # 3. High-priority scan: common bulb DHCP IPs (192.168.1.2 - 192.168.1.30, 192.168.1.100 - 192.168.1.130)
    priority_ips = [f"{subnet}{i}" for i in list(range(2, 31)) + list(range(100, 131))]
    with concurrent.futures.ThreadPoolExecutor(max_workers=50) as executor:
        results = executor.map(scan_single_ip, priority_ips)
        for r in results:
            if r and r[1]:
                save_bulb_ip(r[0])
                BULB_IS_ONLINE = True
                _apply_long_run_stability_settings(r[0])
                return {"found": True, "ip": r[0], "is_ap": False, "details": "Discovered on Subnet (Fast Sweep)"}

    # 4. Full subnet sweep (1-254)
    all_ips = [f"{subnet}{i}" for i in range(1, 255) if f"{subnet}{i}" not in priority_ips]
    with concurrent.futures.ThreadPoolExecutor(max_workers=60) as executor:
        results = executor.map(scan_single_ip, all_ips)
        for r in results:
            if r and r[1]:
                save_bulb_ip(r[0])
                BULB_IS_ONLINE = True
                _apply_long_run_stability_settings(r[0])
                return {"found": True, "ip": r[0], "is_ap": False, "details": "Discovered on Subnet (Full Sweep)"}

    BULB_IS_ONLINE = False
    return {"found": False, "ip": None, "details": "No bulb found"}

def _apply_long_run_stability_settings(ip):
    """Applies optimal Tasmota settings for rock-solid 24/7 run without dropping off Wi-Fi."""
    try:
        # Sleep 0: Zero sleep (lowest latency, eliminates dropped packets during idle)
        # SetOption60 1: Sleep dynamic (keeps WiFi radio awake)
        # WifiConfig 2: Never reset credentials on router drops; auto-retry indefinitely
        # WifiPower 17: Maximum stable transmission strength (17 dBm)
        # TelePeriod 30: 30s heartbeat telemetry
        execute_tasmota("Backlog SetOption60 1; Sleep 0; WifiConfig 2; WifiPower 17; TelePeriod 30", ip=ip, timeout=2.0)
    except Exception:
        pass

def background_watchdog_loop():
    """Continuous background worker ensuring bulletproof 24/7 connectivity and auto-recovery."""
    global BULB_IS_ONLINE, WATCHDOG_LAST_CHECK
    time.sleep(3)
    while True:
        try:
            WATCHDOG_LAST_CHECK = time.time()
            if check_bulb_alive(CURRENT_BULB_IP):
                if not BULB_IS_ONLINE:
                    print(f"[Watchdog] Bulb is ONLINE at {CURRENT_BULB_IP}")
                    _apply_long_run_stability_settings(CURRENT_BULB_IP)
                BULB_IS_ONLINE = True
            else:
                if BULB_IS_ONLINE:
                    print(f"[Watchdog] Bulb lost at {CURRENT_BULB_IP}! Initiating background auto-discovery...")
                BULB_IS_ONLINE = False
                res = auto_discover_bulb()
                if res.get("found") and res.get("ip"):
                    print(f"[Watchdog] Bulb recovered automatically at {res['ip']}")
        except Exception:
            pass
        time.sleep(10)

# Start watchdog daemon thread
watchdog_thread = threading.Thread(target=background_watchdog_loop, daemon=True)
watchdog_thread.start()

class LuminaHandler(http.server.SimpleHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIRECTORY, **kwargs)

    def handle_one_request(self):
        try:
            super().handle_one_request()
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
            self.close_connection = True

    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS, PUT, DELETE")
        self.send_header("Access-Control-Allow-Headers", "*, Content-Type, Authorization, ngrok-skip-browser-warning")
        self.send_header("Access-Control-Max-Age", "86400")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("ngrok-skip-browser-warning", "true")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", "0")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True

    def _send_json(self, status_code, obj):
        body = json.dumps(obj).encode('utf-8')
        self.send_response(status_code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Connection', 'close')
        self.end_headers()
        self.wfile.write(body)
        self.close_connection = True

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        target_ip = params.get('ip', [None])[0]

        if parsed.path == '/api/ping':
            self._send_json(200, {
                "status": "ok",
                "bulb": CURRENT_BULB_IP,
                "bulb_online": BULB_IS_ONLINE,
                "version": "3.2",
                "pairing_ip": "192.168.4.1"
            })
            return

        elif parsed.path == '/api/auto-connect':
            # Instant on-load handshake for web app
            if BULB_IS_ONLINE and check_bulb_alive(CURRENT_BULB_IP):
                self._send_json(200, {
                    "status": "connected",
                    "ip": CURRENT_BULB_IP,
                    "bulb_online": True,
                    "is_ap": (CURRENT_BULB_IP == "192.168.4.1")
                })
                return
            # If offline, run instant discovery
            res = auto_discover_bulb()
            self._send_json(200, {
                "status": "connected" if res.get("found") else "offline",
                "ip": res.get("ip", CURRENT_BULB_IP),
                "bulb_online": res.get("found", False),
                "is_ap": res.get("is_ap", False),
                "details": res.get("details")
            })
            return

        elif parsed.path == '/api/target-ip':
            if 'ip' in params and params['ip'][0]:
                save_bulb_ip(params['ip'][0])
            self._send_json(200, {"ip": CURRENT_BULB_IP})
            return

        elif parsed.path == '/api/discover':
            res = auto_discover_bulb()
            self._send_json(200, res)
            return

        elif parsed.path == '/api/cmd':
            cmd = params.get('c', [''])[0]
            if not cmd:
                self._send_json(400, {"error": "Missing command"})
                return

            status, body = execute_tasmota(cmd, ip=target_ip)
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Connection', 'close')
            self.end_headers()
            self.wfile.write(body)
            self.close_connection = True
            return

        elif parsed.path == '/api/status':
            status, body = execute_tasmota("Status 11", ip=target_ip)
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Connection', 'close')
            self.end_headers()
            self.wfile.write(body)
            self.close_connection = True
            return

        elif parsed.path == '/api/wifi':
            # Status 5 returns full WiFi parameters (SSID, RSSI, IP, Gateway, MAC, etc.)
            status, body = execute_tasmota("Status 5", ip=target_ip)
            if status == 200:
                try:
                    data = json.loads(body.decode('utf-8'))
                    net = data.get('StatusNET', {})
                    self._send_json(200, {
                        "status": "ok",
                        "target_ip": target_ip if target_ip else CURRENT_BULB_IP,
                        "raw": net,
                        "ssid": net.get("SSId", "Unknown"),
                        "bssid": net.get("BSSId", "N/A"),
                        "rssi": net.get("RSSI", 0),
                        "signal_pct": net.get("Signal", 0),
                        "ip": net.get("IPAddress", CURRENT_BULB_IP),
                        "gateway": net.get("Gateway", "N/A"),
                        "mac": net.get("Mac", "N/A"),
                        "hostname": net.get("Hostname", "tasmota")
                    })
                    return
                except Exception:
                    pass
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Connection', 'close')
            self.end_headers()
            self.wfile.write(body)
            self.close_connection = True
            return

        elif parsed.path == '/api/wifiscan':
            # WifiScan 1 prompts Tasmota to scan visible SSIDs
            status, body = execute_tasmota("WifiScan 1", ip=target_ip)
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Connection', 'close')
            self.end_headers()
            self.wfile.write(body)
            self.close_connection = True
            return

        return super().do_GET()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length) if content_length > 0 else b'{}'
        
        try:
            payload = json.loads(post_data.decode('utf-8'))
        except Exception:
            payload = {}

        if parsed.path == '/api/target-ip':
            new_ip = payload.get('ip', '')
            if new_ip:
                save_bulb_ip(new_ip)
                self._send_json(200, {"status": "ok", "bulb_ip": CURRENT_BULB_IP})
            else:
                self._send_json(400, {"error": "Missing 'ip' in payload"})
            return

        elif parsed.path == '/api/wifi':
            # Configure WiFi Credentials:
            # Accepts: ssid, password, ssid2, password2, target_ip, ap_mode_fallback
            ssid = payload.get('ssid', '').strip()
            password = payload.get('password', '').strip()
            ssid2 = payload.get('ssid2', '').strip()
            password2 = payload.get('password2', '').strip()
            target_ip = payload.get('target_ip', CURRENT_BULB_IP).strip()
            ap_policy = payload.get('ap_policy', 2) # 2 = WifiConfig 2 (try SSIDs, if fail open AP)

            if not ssid:
                self._send_json(400, {"error": "Primary SSID is required"})
                return

            # Construct robust Tasmota Backlog command
            cmds = []
            cmds.append(f'SSId1 {ssid}')
            cmds.append(f'Password1 {password}')
            if ssid2:
                cmds.append(f'SSId2 {ssid2}')
                cmds.append(f'Password2 {password2}')
            cmds.append(f'WifiConfig {ap_policy}')
            cmds.append('Restart 1')

            backlog_str = "; ".join(cmds)

            # Try Tasmota Backlog first
            status, body = execute_tasmota(f"Backlog {backlog_str}", ip=target_ip)
            
            # Also dispatch individual commands in case Backlog is disabled in minimal builds
            for c in [f"SSId1 {ssid}", f"Password1 {password}", f"SSId {ssid}", f"Password {password}", f"WifiConfig {ap_policy}"]:
                try:
                    execute_tasmota(c, ip=target_ip)
                except Exception:
                    pass

            # Also attempt direct Tasmota /wi web form post (used by pairing captive portal)
            try:
                wi_url = f"http://{target_ip}/wi"
                form_fields = {
                    's1': ssid,
                    'p1': password,
                    's2': ssid2 or '',
                    'p2': password2 or '',
                    'h': 'Lumina-Smitch',
                    'b': 'save'
                }
                form_data = urllib.parse.urlencode(form_fields).encode('utf-8')
                wi_req = urllib.request.Request(wi_url, data=form_data, headers={
                    'User-Agent': 'Lumina/3.1',
                    'Content-Type': 'application/x-www-form-urlencoded'
                })
                with urllib.request.urlopen(wi_req, timeout=2.0) as wi_resp:
                    pass
            except Exception:
                pass

            # Finally trigger restart after credentials are saved
            try:
                execute_tasmota("Restart 1", ip=target_ip)
            except Exception:
                pass

            if target_ip == '192.168.4.1':
                # Bulb was in pairing mode and is now rebooting to join home network!
                self._send_json(200, {
                    "status": "success",
                    "message": f"WiFi credentials successfully sent to bulb! Bulb is rebooting and joining '{ssid}'.",
                    "target_ip": target_ip,
                    "new_ssid": ssid,
                    "rebooting": True
                })
            else:
                self._send_json(200, {
                    "status": "success",
                    "message": f"WiFi configuration updated! Bulb will connect to '{ssid}' after reboot.",
                    "target_ip": target_ip,
                    "new_ssid": ssid,
                    "rebooting": True
                })
            return

        elif parsed.path == '/api/ota-upgrade':
            target_ip = payload.get('ip', CURRENT_BULB_IP)
            bin_path = os.path.join(os.path.dirname(__file__), "tasmota.bin.gz")
            if not os.path.exists(bin_path):
                self._send_json(404, {"status": "error", "message": "tasmota.bin.gz not found on server"})
                return

            try:
                import uuid
                boundary = '----WebKitFormBoundary' + uuid.uuid4().hex
                with open(bin_path, 'rb') as f:
                    file_bytes = f.read()

                body = (
                    f'--{boundary}\r\n'
                    f'Content-Disposition: form-data; name="u1"; filename="tasmota.bin.gz"\r\n'
                    f'Content-Type: application/octet-stream\r\n\r\n'
                ).encode('utf-8') + file_bytes + f'\r\n--{boundary}--\r\n'.encode('utf-8')

                url = f"http://{target_ip}/u1"
                req = urllib.request.Request(url, data=body, headers={
                    'Content-Type': f'multipart/form-data; boundary={boundary}',
                    'Content-Length': str(len(body)),
                    'User-Agent': 'Lumina/3.1'
                })
                with urllib.request.urlopen(req, timeout=30) as resp:
                    resp_body = resp.read().decode('utf-8', errors='ignore')
                    self._send_json(200, {
                        "status": "ok",
                        "message": "Full Tasmota firmware flashed successfully! Bulb is rebooting with complete light drivers."
                    })
                    return
            except Exception as e:
                self._send_json(500, {"status": "error", "message": f"OTA Flash failed: {str(e)}"})
                return

        elif parsed.path == '/api/cmd':
            cmd = payload.get('c', '')
            target_ip = payload.get('ip', CURRENT_BULB_IP)
            if not cmd:
                self._send_json(400, {"error": "Missing command"})
                return
            status, body = execute_tasmota(cmd, ip=target_ip)
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Connection', 'close')
            self.end_headers()
            self.wfile.write(body)
            self.close_connection = True
            return

        self._send_json(404, {"error": "Not Found"})

class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True

if __name__ == '__main__':
    with ThreadedTCPServer(('0.0.0.0', PORT), LuminaHandler) as httpd:
        print(f"Lumina Studio Server running at http://0.0.0.0:{PORT}/")
        print(f"Active Target Bulb IP: {CURRENT_BULB_IP}")
        print(f"Local URL: http://localhost:{PORT}")
        print(f"Network URL (for Phone): http://192.168.1.9:{PORT}")
        sys.stdout.flush()
        httpd.serve_forever()

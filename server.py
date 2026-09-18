import http.server
import socketserver
import urllib.request
import urllib.parse
import json
import os
import sys
import socket
import concurrent.futures

PORT = 7070
DIRECTORY = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(DIRECTORY, "bulb_config.json")

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

def execute_tasmota(cmd, ip=None):
    target = ip if ip else CURRENT_BULB_IP
    url = f"http://{target}/cm?cmnd={urllib.parse.quote(cmd)}"
    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Lumina/3.1',
        'Referer': f'http://{target}/'
    })
    try:
        with urllib.request.urlopen(req, timeout=3.5) as r:
            return r.status, r.read()
    except Exception as e:
        return 500, json.dumps({"error": str(e), "target_ip": target}).encode()

def scan_single_ip(ip):
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(0.35)
        if s.connect_ex((ip, 80)) == 0:
            s.close()
            try:
                url = f"http://{ip}/cm?cmnd=Status"
                req = urllib.request.Request(url, headers={'User-Agent': 'Lumina/3.1'})
                with urllib.request.urlopen(req, timeout=1.0) as resp:
                    raw = resp.read().decode('utf-8', errors='ignore')
                    if "Status" in raw or "Module" in raw or "FriendlyName" in raw:
                        return (ip, True, raw)
            except Exception:
                pass
        else:
            s.close()
    except Exception:
        pass
    return None

def auto_discover_bulb(subnet="192.168.1."):
    # First check 192.168.4.1 (standard Tasmota / ESP AP mode)
    ap_res = scan_single_ip("192.168.4.1")
    if ap_res:
        return {"found": True, "ip": "192.168.4.1", "is_ap": True, "details": "Smitch / Tasmota Pairing Hotspot"}

    # Next check current configured IP
    current_res = scan_single_ip(CURRENT_BULB_IP)
    if current_res:
        return {"found": True, "ip": CURRENT_BULB_IP, "is_ap": False, "details": "Configured Bulb Active"}

    # Parallel scan across subnet 1-254
    ips = [f"{subnet}{i}" for i in range(1, 255)]
    with concurrent.futures.ThreadPoolExecutor(max_workers=60) as executor:
        results = executor.map(scan_single_ip, ips)
        for r in results:
            if r and r[1]:
                save_bulb_ip(r[0])
                return {"found": True, "ip": r[0], "is_ap": False, "details": "Discovered on Subnet"}

    return {"found": False, "ip": None, "details": "No bulb found on subnet or AP"}

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
                "version": "3.1",
                "pairing_ip": "192.168.4.1"
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

            # Try Tasmota HTTP API first
            status, body = execute_tasmota(f"Backlog {backlog_str}", ip=target_ip)

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

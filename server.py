import http.server
import socketserver
import urllib.request
import urllib.parse
import json
import os
import sys

BULB_IP = "192.168.1.11"
PORT = 7070
DIRECTORY = os.path.dirname(os.path.abspath(__file__))

def execute_tasmota(cmd):
    url = f"http://{BULB_IP}/cm?cmnd={urllib.parse.quote(cmd)}"
    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0',
        'Referer': f'http://{BULB_IP}/'
    })
    try:
        with urllib.request.urlopen(req, timeout=4) as r:
            return r.status, r.read()
    except Exception as e:
        return 500, json.dumps({"error": str(e)}).encode()

class LuminaHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIRECTORY, **kwargs)

    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        
        if parsed.path == '/api/cmd':
            params = urllib.parse.parse_qs(parsed.query)
            cmd = params.get('c', [''])[0]
            if not cmd:
                self.send_response(400)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(b'{"error":"Missing command"}')
                return

            status, body = execute_tasmota(cmd)
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(body)
            return

        elif parsed.path == '/api/status':
            status, body = execute_tasmota("Status 11")
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(body)
            return

        elif parsed.path == '/api/ping':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(b'{"status":"ok","bulb":"192.168.1.11"}')
            return

        return super().do_GET()

if __name__ == '__main__':
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(('0.0.0.0', PORT), LuminaHandler) as httpd:
        print(f"Lumina Studio Server running at http://0.0.0.0:{PORT}/")
        print(f"Local URL: http://localhost:{PORT}")
        print(f"Network URL (for Phone): http://192.168.1.9:{PORT}")
        sys.stdout.flush()
        httpd.serve_forever()

#!/usr/bin/env python3
"""Simple trade dashboard server."""
import json
import os
from http.server import HTTPServer, SimpleHTTPRequestHandler

TRADES_FILE = "/root/iqoption-bot/experiments/results/rho_real_trades.json"
PORT = 8088

class DashboardHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory="/root/iqoption-bot/dashboard", **kwargs)
    
    def do_GET(self):
        if self.path == '/data':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            try:
                with open(TRADES_FILE) as f:
                    data = json.load(f)
                self.wfile.write(json.dumps(data).encode())
            except:
                self.wfile.write(b'[]')
        elif self.path == '/health':
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()
            self.wfile.write(b'ok')
        else:
            super().do_GET()
    
    def log_message(self, format, *args):
        pass  # Suppress logs

if __name__ == '__main__':
    server = HTTPServer(('0.0.0.0', PORT), DashboardHandler)
    print(f"Dashboard running on port {PORT}")
    server.serve_forever()

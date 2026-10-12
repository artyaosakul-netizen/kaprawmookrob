"""Vercel Serverless Function — proxies Gemini API calls with server-side API key"""

import json
import os
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            request_data = json.loads(body)

            # คีย์จริงจาก cURL (แก้ลงท้ายด้วย NlA แอลเล็ก)
            api_key = "AQ.Ab8RN6Kafmz2BAw8O5fldLD6jxtHMUDBpfDOssKanRDtqb2NlA"
            # ใช้โมเดล gemini-flash-latest ตามคำสั่ง cURL ตรงๆ
            model = "gemini-flash-latest"

            if not api_key:
                self._send_json(500, {"error": "GEMINI_API_KEY not configured on server"})
                return

            # เรียก Endpoint ตาม cURL ของ Google
            gemini_url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

            req = urllib.request.Request(
                gemini_url,
                data=json.dumps(request_data).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "X-goog-api-key": api_key,
                },
                method="POST",
            )

            with urllib.request.urlopen(req, timeout=60) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                self._send_json(200, result)

        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8", errors="replace")
            try:
                error_json = json.loads(error_body)
            except json.JSONDecodeError:
                error_json = {"error": error_body}
            self._send_json(e.code, error_json)

        except Exception as e:
            self._send_json(500, {"error": str(e)})

    def _send_json(self, status, data):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-goog-api-key")
        self.end_headers()

    def log_message(self, fmt, *args):
        return

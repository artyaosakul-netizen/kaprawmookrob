"""Vercel Function สำหรับ GET สถานะ Gemini และ POST ข้อความ"""

from http.server import BaseHTTPRequestHandler

from server import process_json_request, provider_status, send_json


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        send_json(self, 200, provider_status())

    def do_POST(self):
        status, data = process_json_request(self.headers, self.rfile)
        send_json(self, status, data)

    def log_message(self, message_format, *args):
        # ไม่พิมพ์ Prompt, API Key หรือ Raw Response
        return

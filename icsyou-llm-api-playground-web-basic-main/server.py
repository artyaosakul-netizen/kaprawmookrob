"""Gemini backend ที่ใช้ร่วมกันได้ทั้ง Local Server และ Vercel Function"""

import json
import os
import re
import shutil
import socket
import ssl
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HOST = "127.0.0.1"
PORT = 8000
REQUEST_TIMEOUT_SECONDS = 30
MAX_REQUEST_BYTES = 32 * 1024
MAX_PROVIDER_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_MESSAGE_LENGTH = 4_000
MAX_SYSTEM_PROMPT_LENGTH = 2_000

PROJECT_DIR = Path(__file__).resolve().parent
ENV_FILE = PROJECT_DIR / ".env"
ENV_EXAMPLE_FILE = PROJECT_DIR / ".env.example"
GEMINI_API_ROOT = "https://generativelanguage.googleapis.com/v1beta"


class SafeError(Exception):
    """ข้อผิดพลาดที่ส่งให้ Browser ได้โดยไม่เปิดเผยข้อมูลลับ"""

    def __init__(self, message, status=400, code="validation_error", learning=None):
        super().__init__(message)
        self.message = message
        self.status = status
        self.code = code
        self.learning = learning


def read_env_file(path):
    """อ่าน NAME=value, ข้ามบรรทัดว่าง/คอมเมนต์ และรองรับ quote"""
    values = {}
    with path.open("r", encoding="utf-8-sig") as env_file:
        for raw_line in env_file:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue

            name, value = line.split("=", 1)
            name, value = name.strip(), value.strip()
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
                continue
            if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
                value = value[1:-1]
            values[name] = value
    return values


def load_settings():
    """Local ใช้ .env ก่อน ส่วน Vercel ใช้ System Environment Variables"""
    source = read_env_file(ENV_FILE) if ENV_FILE.exists() else os.environ
    return {
        "api_key": str(source.get("GEMINI_API_KEY", "")).strip(),
        "model": str(source.get("GEMINI_MODEL", "")).strip(),
    }


def ensure_env_file():
    if ENV_FILE.exists():
        return False
    if not ENV_EXAMPLE_FILE.exists():
        raise SafeError("ไม่พบไฟล์ .env.example จึงสร้าง .env ไม่ได้", 500)
    shutil.copyfile(ENV_EXAMPLE_FILE, ENV_FILE)
    return True


def provider_status():
    settings = load_settings()
    configured = bool(settings["api_key"] and settings["model"])

    if configured:
        message = f"Gemini พร้อมใช้งาน · Model: {settings['model']}"
    elif not settings["api_key"]:
        message = "ยังไม่ได้ตั้งค่า GEMINI_API_KEY"
    else:
        message = "ยังไม่ได้ตั้งค่า GEMINI_MODEL"

    return {
        "success": True,
        "provider": {
            "id": "gemini",
            "label": "Google Gemini",
            "configured": configured,
            "model": settings["model"] or None,
            "message": message,
        },
    }


def read_json_body(headers, stream):
    content_type = headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
    if content_type != "application/json":
        raise SafeError(
            "กรุณาส่งข้อมูลแบบ JSON และกำหนด Content-Type: application/json",
            415,
            "invalid_content_type",
        )

    try:
        length = int(headers.get("Content-Length", "0"))
    except ValueError as error:
        raise SafeError("ขนาด Request ไม่ถูกต้อง", 400, "invalid_request") from error

    if length <= 0:
        raise SafeError("ไม่พบข้อมูล JSON", 400, "empty_body")
    if length > MAX_REQUEST_BYTES:
        raise SafeError("Request มีขนาดใหญ่เกินไป", 413, "request_too_large")

    try:
        data = json.loads(stream.read(length).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SafeError("JSON ไม่ถูกต้อง", 400, "invalid_json") from error

    if not isinstance(data, dict):
        raise SafeError("JSON ต้องเป็น Object", 400, "invalid_json")
    return data


def validate_chat_data(data):
    if data.get("provider") not in {None, "gemini"}:
        raise SafeError("เว็บไซต์รุ่นนี้รองรับเฉพาะ Gemini", 400, "unknown_provider")

    system_prompt = data.get("systemPrompt", "")
    message = data.get("message", "")

    if not isinstance(system_prompt, str) or not isinstance(message, str):
        raise SafeError("System Prompt และข้อความต้องเป็นตัวอักษร", 400, "invalid_input")
    if not message.strip():
        raise SafeError("กรุณาพิมพ์ข้อความก่อนส่งให้ AI", 400, "empty_message")
    if len(message) > MAX_MESSAGE_LENGTH:
        raise SafeError("ข้อความยาวเกิน 4,000 ตัวอักษร", 400, "message_too_long")
    if len(system_prompt) > MAX_SYSTEM_PROMPT_LENGTH:
        raise SafeError("System Prompt ยาวเกิน 2,000 ตัวอักษร", 400, "system_prompt_too_long")

    return system_prompt.strip(), message.strip(), data.get("learningMode") is True


def gemini_request_data(system_prompt, message, model):
    body = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": message}],
            }
        ]
    }
    if system_prompt:
        body["systemInstruction"] = {"parts": [{"text": system_prompt}]}

    model_id = model.removeprefix("models/")
    safe_model = urllib.parse.quote(model_id, safe="-._")
    path = f"/v1beta/models/{safe_model}:generateContent"
    return body, path, f"{GEMINI_API_ROOT}/models/{safe_model}:generateContent"


def safe_request_preview(body, path):
    return {
        "method": "POST",
        "endpointPath": path,
        "headers": {"Content-Type": "application/json"},
        "secretNote": "Python เพิ่ม API Key ใน Header จริง แต่ไม่ส่ง Header นั้นกลับ Browser",
        "body": body,
    }


def learning_trace(preview, status, body, code):
    return {
        "providerRequest": preview,
        "providerResponse": {"httpStatus": status, "body": body},
        "diagnosticCode": code,
    }


def attach_learning(error, preview, status=None, body=None):
    error.learning = learning_trace(
        preview,
        status,
        body or {"note": error.message},
        error.code,
    )
    return error


def usage_from_gemini(data):
    usage = data.get("usageMetadata", {})
    input_tokens = usage.get("promptTokenCount")
    output_tokens = usage.get("candidatesTokenCount")
    total_tokens = usage.get("totalTokenCount")
    return {
        "inputTokens": input_tokens if isinstance(input_tokens, int) else None,
        "outputTokens": output_tokens if isinstance(output_tokens, int) else None,
        "totalTokens": total_tokens if isinstance(total_tokens, int) else None,
    }


def answer_from_gemini(data):
    candidates = data.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        block_reason = data.get("promptFeedback", {}).get("blockReason")
        if block_reason:
            raise SafeError(
                "Gemini ไม่สามารถตอบข้อความนี้ได้ กรุณาปรับคำถามแล้วลองใหม่",
                502,
                "content_blocked",
            )
        raise SafeError("Gemini ตอบกลับมาในรูปแบบที่อ่านไม่ได้", 502, "invalid_provider_response")

    parts = candidates[0].get("content", {}).get("parts", [])
    answer = "".join(
        part.get("text", "") for part in parts if isinstance(part, dict)
    ).strip()
    if not answer:
        raise SafeError("Gemini ไม่ได้ส่งข้อความคำตอบกลับมา", 502, "empty_provider_answer")
    return answer


def provider_error(status, detail):
    detail = detail.lower()

    if status in {400, 401, 403} and any(
        word in detail for word in ("api key", "api_key", "key invalid", "key blocked")
    ):
        return SafeError(
            "API Key ไม่ถูกต้อง ถูกบล็อก หรือไม่มีสิทธิ์ใช้งาน",
            502,
            "authentication_error",
        )
    if status in {401, 403}:
        if any(word in detail for word in ("billing", "credit", "payment")):
            return SafeError("บัญชีอาจต้องเปิด Billing", 502, "billing_required")
        return SafeError(
            "API Key ไม่ถูกต้อง ถูกบล็อก หรือไม่มีสิทธิ์ใช้งาน",
            502,
            "authentication_error",
        )
    if status == 404 or (status == 400 and "model" in detail):
        return SafeError(
            "Model นี้ไม่มีให้ใช้งาน กรุณาตรวจชื่อ GEMINI_MODEL",
            502,
            "model_not_available",
        )
    if status == 429:
        if "quota" in detail or "resource_exhausted" in detail:
            return SafeError(
                "โควตาหรือเครดิตอาจหมด กรุณาตรวจบัญชี Gemini",
                502,
                "quota_exhausted",
            )
        return SafeError(
            "ส่งคำขอบ่อยเกินไป กรุณารอสักครู่",
            502,
            "rate_limited",
        )
    if status in {500, 502, 503}:
        return SafeError(
            "ผู้ให้บริการ AI ยังไม่พร้อม กรุณาลองใหม่ภายหลัง",
            502,
            "provider_unavailable",
        )
    if status == 504:
        return SafeError("Provider ใช้เวลาตอบนานเกินไป", 504, "provider_timeout")
    if status in {400, 402} and any(
        word in detail for word in ("billing", "credit", "payment")
    ):
        return SafeError("บัญชีอาจต้องเปิด Billing", 502, "billing_required")
    return SafeError(
        "Gemini ปฏิเสธคำขอ กรุณาตรวจข้อความและการตั้งค่า",
        502,
        "provider_request_failed",
    )


def network_error(reason):
    if isinstance(reason, (socket.timeout, TimeoutError)):
        return SafeError("Provider ใช้เวลาตอบนานเกินไป", 504, "provider_timeout")
    if isinstance(reason, ssl.SSLCertVerificationError):
        return SafeError(
            "เชื่อมต่อแบบปลอดภัยไม่ได้ กรุณาตรวจวันเวลาและ Certificate ของเครื่อง",
            502,
            "certificate_error",
        )
    if isinstance(reason, socket.gaierror):
        return SafeError(
            "ไม่พบที่อยู่ของผู้ให้บริการ AI กรุณาตรวจอินเทอร์เน็ตหรือ DNS",
            502,
            "dns_error",
        )
    if isinstance(reason, PermissionError):
        return SafeError(
            "Python หรือ Firewall ถูกปิดกั้นไม่ให้ออกอินเทอร์เน็ต",
            502,
            "network_permission_error",
        )
    return SafeError("ไม่สามารถติดต่อผู้ให้บริการ AI ได้", 502, "network_error")


def call_gemini(system_prompt, message, settings):
    body, path, url = gemini_request_data(system_prompt, message, settings["model"])
    preview = safe_request_preview(body, path)
    encoded_body = json.dumps(body, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=encoded_body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": settings["api_key"],
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            response_bytes = response.read(MAX_PROVIDER_RESPONSE_BYTES + 1)
            status = response.status
    except urllib.error.HTTPError as error:
        detail = error.read(64 * 1024).decode("utf-8", errors="replace")
        safe_error = provider_error(error.code, detail)
        raise attach_learning(safe_error, preview, error.code) from error
    except urllib.error.URLError as error:
        safe_error = network_error(error.reason)
        raise attach_learning(safe_error, preview) from error
    except (socket.timeout, TimeoutError, OSError) as error:
        safe_error = network_error(error)
        raise attach_learning(safe_error, preview) from error

    if len(response_bytes) > MAX_PROVIDER_RESPONSE_BYTES:
        raise SafeError("Gemini ส่งข้อมูลกลับมามากเกินไป", 502, "provider_response_too_large")

    try:
        response_data = json.loads(response_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SafeError(
            "Gemini ตอบกลับมาในรูปแบบที่อ่านไม่ได้",
            502,
            "invalid_provider_response",
        ) from error

    if not isinstance(response_data, dict):
        raise SafeError(
            "Gemini ตอบกลับมาในรูปแบบที่อ่านไม่ได้",
            502,
            "invalid_provider_response",
        )

    try:
        answer = answer_from_gemini(response_data)
    except SafeError as error:
        raise attach_learning(error, preview, status, response_data) from error

    return {
        "answer": answer,
        "usage": usage_from_gemini(response_data),
        "learning": learning_trace(preview, status, response_data, "ok"),
    }


def error_response(error, started_at, include_learning=False):
    result = {
        "success": False,
        "error": error.message,
        "code": error.code,
        "durationMs": round((time.perf_counter() - started_at) * 1000),
    }
    if include_learning and error.learning:
        result["learning"] = error.learning
    return result


def process_chat_data(data):
    started_at = time.perf_counter()
    include_learning = isinstance(data, dict) and data.get("learningMode") is True

    try:
        system_prompt, message, include_learning = validate_chat_data(data)
        settings = load_settings()
        if not settings["api_key"]:
            raise SafeError(
                "ยังไม่ได้ตั้งค่า GEMINI_API_KEY",
                400,
                "missing_api_key",
            )
        if not settings["model"]:
            raise SafeError(
                "ยังไม่ได้ตั้งค่า GEMINI_MODEL",
                400,
                "missing_model",
            )

        provider_result = call_gemini(system_prompt, message, settings)
        result = {
            "success": True,
            "provider": "gemini",
            "model": settings["model"],
            "answer": provider_result["answer"],
            "usage": provider_result["usage"],
            "durationMs": round((time.perf_counter() - started_at) * 1000),
        }
        if include_learning:
            result["learning"] = provider_result["learning"]
        return 200, result
    except SafeError as error:
        return error.status, error_response(error, started_at, include_learning)
    except Exception:
        # ไม่ส่ง Stack Trace หรือ Raw Error ไปยัง Browser
        error = SafeError(
            "เกิดข้อผิดพลาดใน Backend กรุณาลองใหม่",
            500,
            "internal_error",
        )
        return 500, error_response(error, started_at)


def process_json_request(headers, stream):
    started_at = time.perf_counter()
    try:
        return process_chat_data(read_json_body(headers, stream))
    except SafeError as error:
        return error.status, error_response(error, started_at)


def send_json(handler, status, data):
    body = json.dumps(data, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("X-Content-Type-Options", "nosniff")
    handler.end_headers()
    handler.wfile.write(body)


class LocalRequestHandler(BaseHTTPRequestHandler):
    STATIC_FILES = {
        "/": ("index.html", "text/html; charset=utf-8"),
        "/index.html": ("index.html", "text/html; charset=utf-8"),
        "/style.css": ("style.css", "text/css; charset=utf-8"),
        "/script.js": ("script.js", "text/javascript; charset=utf-8"),
    }

    def do_GET(self):
        path = urllib.parse.urlsplit(self.path).path
        if path == "/api/chat":
            send_json(self, 200, provider_status())
            return

        static_file = self.STATIC_FILES.get(path)
        if not static_file:
            send_json(self, 404, {"success": False, "error": "ไม่พบหน้าที่ต้องการ"})
            return

        filename, content_type = static_file
        try:
            body = (PROJECT_DIR / filename).read_bytes()
        except OSError:
            send_json(self, 500, {"success": False, "error": "อ่านไฟล์เว็บไซต์ไม่ได้"})
            return

        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if urllib.parse.urlsplit(self.path).path != "/api/chat": 
            send_json(self, 404, {"success": False, "error": "ไม่พบ API ที่ต้องการ"})
            return
        status, data = process_json_request(self.headers, self.rfile)
        send_json(self, status, data)

    def log_message(self, message_format, *args):
        # Log เฉพาะ Method/Path/Status ที่ BaseHTTPRequestHandler ส่งมา
        print(f"HTTP {self.address_string()} - {message_format % args}")


def print_check():
    settings = load_settings()
    print(f"Python: {sys.version.split()[0]}")
    print(f".env: {'พบ' if ENV_FILE.exists() else 'ไม่พบ'}")
    print(f"Gemini API Key: {'มี' if settings['api_key'] else 'ไม่มี'}")
    print(f"Gemini Model: {settings['model'] or 'ยังไม่ได้ตั้งค่า'}")


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    if len(sys.argv) > 1:
        if sys.argv[1:] == ["--check"]:
            print_check()
            return
        print("คำสั่งที่รองรับ: python server.py หรือ python server.py --check")
        raise SystemExit(2)

    try:
        created = ensure_env_file()
    except SafeError as error:
        print(error.message)
        raise SystemExit(1) from error

    if created:
        print("สร้าง .env จาก .env.example แล้ว กรุณาใส่ Gemini API Key")

    print_check()
    try:
        server = ThreadingHTTPServer((HOST, PORT), LocalRequestHandler)
    except OSError:
        print(f"เปิดพอร์ต {PORT} ไม่ได้ พอร์ตอาจถูกใช้งานอยู่")
        print("กรุณาปิด Server เดิม แล้วลองใหม่")
        raise SystemExit(1)

    url = f"http://{HOST}:{PORT}"
    print(f"เปิดเว็บไซต์ที่ {url}")
    print("หยุด Server ด้วย Ctrl+C")
    threading.Timer(0.7, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nหยุด Server แล้ว")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()

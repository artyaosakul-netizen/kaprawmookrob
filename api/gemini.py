"""Vercel Serverless Function: Gemini API proxy.

Required Vercel Environment Variable:
    GEMINI_API_KEY

Primary model is retried once with a short exponential backoff. If it still
fails, the function tries two fallback models. API keys and request contents
are never written to logs.
"""

import json
import os
import random
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler


PRIMARY_MODEL = "gemini-3.8-flash"
# Try a lightweight model first as an alternate capacity path, then other models.
FALLBACK_MODELS = [
    "gemini-3.5-flash-lite",
    "gemini-3.7-flash",
    "gemini-3.6-flash",
]

RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504}
MAX_REQUEST_BYTES = 10_000_000
REQUEST_TIMEOUT_SECONDS = 5
PRIMARY_ATTEMPTS = 2


def log_event(message):
    print(f"[api/gemini] {message}", flush=True)


def safe_error_message(data):
    if not isinstance(data, dict):
        return str(data)[:800]
    error = data.get("error", data)
    if not isinstance(error, dict):
        return str(error)[:800]
    code = error.get("code")
    status = error.get("status")
    message = error.get("message") or status or str(error)
    parts = []
    if code is not None:
        parts.append(f"code={code}")
    if status:
        parts.append(f"status={status}")
    parts.append(f"message={str(message)[:800]}")
    return "; ".join(parts)


def call_gemini(model, request_data, api_key):
    url = (
        "https://generativelanguage.googleapis.com/"
        f"v1beta/models/{model}:generateContent"
    )
    request = urllib.request.Request(
        url,
        data=json.dumps(request_data).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": api_key,
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
        raw = response.read().decode("utf-8", errors="replace")
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return response.status, {
                "error": {"message": "Gemini returned an invalid JSON response"}
            }
        return response.status, data


def call_model(model, request_data, api_key, attempts=1):
    """Return (status, JSON response). Retry only transient failures."""
    last_status = 503
    last_result = {"error": {"message": "Gemini request did not complete"}}

    for attempt in range(1, attempts + 1):
        try:
            last_status, last_result = call_gemini(model, request_data, api_key)
        except urllib.error.HTTPError as exc:
            last_status = exc.code
            try:
                last_result = json.loads(exc.read().decode("utf-8", errors="replace"))
            except (json.JSONDecodeError, UnicodeDecodeError, OSError):
                last_result = {"error": {"message": f"HTTP {exc.code}: {exc.reason}"}}
        except (TimeoutError, OSError, urllib.error.URLError) as exc:
            last_status = 503
            last_result = {
                "error": {"message": f"Connection/timeout error: {type(exc).__name__}: {str(exc)[:400]}"}
            }
        except Exception as exc:
            last_status = 500
            last_result = {
                "error": {"message": f"Unexpected error: {type(exc).__name__}: {str(exc)[:400]}"}
            }

        if last_status == 200:
            log_event(f"model={model} attempt={attempt} status=200")
            return last_status, last_result

        log_event(
            f"model={model} attempt={attempt} status={last_status} "
            f"error={safe_error_message(last_result)}"
        )

        if last_status not in RETRYABLE_STATUS or attempt == attempts:
            break

        # Brief exponential backoff with jitter. Keep it short for serverless runtimes.
        delay = min(1.5 * (2 ** (attempt - 1)), 3.0) + random.uniform(0, 0.25)
        log_event(f"retry_wait model={model} seconds={delay:.2f}")
        time.sleep(delay)

    return last_status, last_result


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            try:
                content_length = int(self.headers.get("Content-Length", "0"))
            except (TypeError, ValueError):
                self._send_json(400, {"error": {"message": "Invalid Content-Length"}})
                return

            if content_length <= 0 or content_length > MAX_REQUEST_BYTES:
                self._send_json(400, {"error": {"message": "Invalid request body size"}})
                return

            body = self.rfile.read(content_length)
            try:
                request_data = json.loads(body.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                self._send_json(400, {"error": {"message": "Invalid JSON request"}})
                return

            if not isinstance(request_data, dict):
                self._send_json(400, {"error": {"message": "JSON request must be an object"}})
                return

            api_key = os.environ.get("GEMINI_API_KEY")
            if not api_key:
                log_event("configuration_error=GEMINI_API_KEY is missing")
                self._send_json(500, {"error": {"message": "GEMINI_API_KEY not configured on server"}})
                return

            log_event("request_started route=/api/gemini")
            models = [(PRIMARY_MODEL, PRIMARY_ATTEMPTS)] + [
                (model, 1) for model in FALLBACK_MODELS
            ]
            failures = []

            for index, (model, attempts) in enumerate(models):
                if index > 0:
                    log_event(f"trying_fallback model={model}")

                status, result = call_model(model, request_data, api_key, attempts)
                if status == 200:
                    if index > 0:
                        log_event(f"fallback_succeeded model={model}")
                    self._send_json(200, result)
                    return

                failures.append({
                    "model": model,
                    "status": status,
                    "error": result.get("error", {}) if isinstance(result, dict) else {},
                })

                # Auth, permission, or malformed-request errors won't be fixed
                # by switching models, so stop and return the useful error.
                if status in {400, 401, 403}:
                    break

            log_event("all_models_failed " + "; ".join(
                f"{item['model']}={item['status']}" for item in failures
            ))
            final_status = failures[-1]["status"] if failures else 503
            if final_status < 400 or final_status > 599:
                final_status = 503
            self._send_json(final_status, {
                "error": {
                    "message": "All configured Gemini models failed",
                    "failures": failures,
                }
            })

        except Exception as exc:
            log_event(f"handler_error={type(exc).__name__}: {str(exc)[:400]}")
            self._send_json(500, {
                "error": {
                    "message": "Internal server error",
                    "detail": f"{type(exc).__name__}: {str(exc)[:250]}",
                }
            })

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _send_json(self, status, data):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        return

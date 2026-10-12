"""Vercel Serverless Function — Gemini API proxy"""

import json
import os
import random
import time
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler


# ============================================================
# Gemini models
# ============================================================

PRIMARY_MODEL = "gemini-3.8-flash"
FALLBACK_MODEL = "gemini-3.6-flash"


# Retry เฉพาะ error ที่มีโอกาสเป็นปัญหาชั่วคราว
# ไม่ใส่ 429 เพื่อป้องกันการยิง API ซ้ำหลายครั้ง
RETRYABLE_STATUS = {
    408,
    500,
    502,
    503,
    504,
}


# ============================================================
# Call Gemini API
# ============================================================

def call_gemini(model, request_data, api_key):
    """Call Gemini API and return (status_code, response_data)."""

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

    try:
        with urllib.request.urlopen(
            request,
            timeout=25
        ) as response:

            raw = response.read().decode(
                "utf-8",
                errors="replace"
            )

            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                data = {
                    "error": {
                        "message": "Invalid JSON response from Gemini"
                    }
                }

            return response.status, data

    except urllib.error.HTTPError as error:

        try:
            raw = error.read().decode(
                "utf-8",
                errors="replace"
            )

            data = json.loads(raw)

        except (json.JSONDecodeError, ValueError):

            data = {
                "error": {
                    "message": "Gemini API request failed"
                }
            }

        return error.code, data


# ============================================================
# Retry temporary errors
# ============================================================

def call_with_retry(model, request_data, api_key):
    """
    Retry temporary server/network errors.

    IMPORTANT:
    429 is NOT retried here.
    This prevents one user request from generating
    multiple Gemini requests when the quota is exhausted.
    """

    last_status = 500

    last_data = {
        "error": {
            "message": "Gemini request failed"
        }
    }

    for attempt in range(3):

        try:

            status, data = call_gemini(
                model,
                request_data,
                api_key
            )

            # สำเร็จ
            if status == 200:
                return status, data

            # 429 = rate limit / quota
            # ไม่ retry
            if status == 429:
                return status, data

            # Error ที่ไม่ควร retry
            if status not in RETRYABLE_STATUS:
                return status, data

            last_status = status
            last_data = data

        except (
            TimeoutError,
            OSError,
            urllib.error.URLError
        ) as error:

            last_status = 503

            last_data = {
                "error": {
                    "message": (
                        "Temporary network or timeout error: "
                        + str(error)[:300]
                    )
                }
            }

        # Retry เฉพาะ temporary errors
        if attempt < 2:

            delay = (
                (2 ** attempt)
                + random.uniform(0, 0.5)
            )

            time.sleep(delay)

    return last_status, last_data


# ============================================================
# Vercel Handler
# ============================================================

class handler(BaseHTTPRequestHandler):

    # --------------------------------------------------------
    # POST
    # --------------------------------------------------------

    def do_POST(self):

        try:

            # ------------------------------------------------
            # Check body size
            # ------------------------------------------------

            content_length = int(
                self.headers.get(
                    "Content-Length",
                    "0"
                )
            )

            if (
                content_length <= 0
                or content_length > 10_000_000
            ):

                self._send_json(
                    400,
                    {
                        "error": {
                            "message":
                            "Invalid request body size"
                        }
                    }
                )

                return

            # ------------------------------------------------
            # Read JSON
            # ------------------------------------------------

            body = self.rfile.read(
                content_length
            )

            request_data = json.loads(body)

            # ------------------------------------------------
            # Read API key
            # ------------------------------------------------

            api_key = os.environ.get(
                "GEMINI_API_KEY"
            )

            if not api_key:

                self._send_json(
                    500,
                    {
                        "error": {
                            "message":
                            "GEMINI_API_KEY not configured on server"
                        }
                    }
                )

                return

            # =================================================
            # PRIMARY MODEL
            # =================================================

            status, result = call_with_retry(
                PRIMARY_MODEL,
                request_data,
                api_key
            )

            # สำเร็จ
            if status == 200:

                self._send_json(
                    200,
                    result
                )

                return

            # =================================================
            # 429 RATE LIMIT
            # =================================================

            if status == 429:

                self._send_json(
                    429,
                    {
                        "error": {
                            "message": (
                                "Gemini API มีการจำกัดจำนวนคำขอ "
                                "หรือ quota ถูกใช้งานถึงขีดจำกัด "
                                "กรุณารอสักครู่แล้วลองใหม่"
                            ),
                            "type": "RATE_LIMIT",
                            "status": 429,
                            "model": PRIMARY_MODEL,
                            "details": result.get(
                                "error",
                                {}
                            )
                        }
                    }
                )

                return

            # =================================================
            # Non-retryable error
            # =================================================

            if (
                status not in RETRYABLE_STATUS
                and status != 404
            ):

                self._send_json(
                    status,
                    {
                        "error": {
                            "message":
                            "Gemini API request failed",
                            "status": status,
                            "details":
                            result.get(
                                "error",
                                {}
                            )
                        }
                    }
                )

                return

            # =================================================
            # FALLBACK MODEL
            # =================================================

            fallback_status, fallback_result = (
                call_with_retry(
                    FALLBACK_MODEL,
                    request_data,
                    api_key
                )
            )

            # Fallback สำเร็จ
            if fallback_status == 200:

                self._send_json(
                    200,
                    fallback_result
                )

                return

            # Fallback ก็ 429
            if fallback_status == 429:

                self._send_json(
                    429,
                    {
                        "error": {
                            "message": (
                                "Gemini API rate limit "
                                "หรือ quota ถูกใช้งานถึงขีดจำกัด"
                            ),
                            "type": "RATE_LIMIT",
                            "status": 429,
                            "primary_model":
                                PRIMARY_MODEL,
                            "fallback_model":
                                FALLBACK_MODEL,
                            "details":
                                fallback_result.get(
                                    "error",
                                    {}
                                )
                        }
                    }
                )

                return

            # =================================================
            # Both models failed
            # =================================================

            self._send_json(
                fallback_status,
                {
                    "error": {
                        "message":
                            "Both Gemini models failed",

                        "primary_model":
                            PRIMARY_MODEL,

                        "primary_status":
                            status,

                        "primary_error":
                            result.get(
                                "error",
                                {}
                            ),

                        "fallback_model":
                            FALLBACK_MODEL,

                        "fallback_status":
                            fallback_status,

                        "fallback_error":
                            fallback_result.get(
                                "error",
                                {}
                            ),
                    }
                }
            )

        # =====================================================
        # Invalid JSON
        # =====================================================

        except json.JSONDecodeError:

            self._send_json(
                400,
                {
                    "error": {
                        "message":
                            "Invalid JSON request"
                    }
                }
            )

        # =====================================================
        # Unexpected error
        # =====================================================

        except Exception as error:

            self._send_json(
                500,
                {
                    "error": {
                        "message":
                            "Internal server error",

                        "detail":
                            str(error)[:300]
                    }
                }
            )

    # --------------------------------------------------------
    # Send JSON response
    # --------------------------------------------------------

    def _send_json(self, status, data):

        body = json.dumps(
            data,
            ensure_ascii=False
        ).encode("utf-8")

        self.send_response(status)

        self.send_header(
            "Content-Type",
            "application/json; charset=utf-8"
        )

        self.send_header(
            "Access-Control-Allow-Origin",
            "*"
        )

        self.send_header(
            "Access-Control-Allow-Methods",
            "POST, OPTIONS"
        )

        self.send_header(
            "Access-Control-Allow-Headers",
            "Content-Type"
        )

        self.send_header(
            "Content-Length",
            str(len(body))
        )

        self.end_headers()

        self.wfile.write(body)

    # --------------------------------------------------------
    # OPTIONS / CORS
    # --------------------------------------------------------

    def do_OPTIONS(self):

        self.send_response(200)

        self.send_header(
            "Access-Control-Allow-Origin",
            "*"
        )

        self.send_header(
            "Access-Control-Allow-Methods",
            "POST, OPTIONS"
        )

        self.send_header(
            "Access-Control-Allow-Headers",
            "Content-Type"
        )

        self.end_headers()

    # --------------------------------------------------------
    # Disable default HTTP logs
    # --------------------------------------------------------

    def log_message(self, fmt, *args):
        return

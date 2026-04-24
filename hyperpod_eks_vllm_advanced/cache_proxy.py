#!/usr/bin/env python3
"""Redis L3 cache proxy for vLLM inference.

Runs as a sidecar or standalone proxy that intercepts incoming inference
requests, checks Redis for cached prompt-prefix metadata, and forwards
to the vLLM backend.  On Redis failure the cache is bypassed transparently.

Usage:
    python cache_proxy.py \
        --listen-port 8080 \
        --vllm-url http://localhost:8000 \
        --redis-url redis://localhost:6379 \
        --ttl 3600
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import socket
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Any, Dict, Optional
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

logger = logging.getLogger("cache_proxy")


# ---------------------------------------------------------------------------
# Pure helper – importable for property tests
# ---------------------------------------------------------------------------

def compute_cache_key(prompt: str) -> str:
    """Return the SHA-256 hex digest of *prompt*.

    This is a pure, deterministic function: the same prompt always produces
    the same digest.
    """
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Redis helpers
# ---------------------------------------------------------------------------

def _get_redis_client(redis_url: str):
    """Return a ``redis.Redis`` client or *None* on import / connect error."""
    try:
        import redis as _redis
        return _redis.Redis.from_url(redis_url, socket_connect_timeout=1, socket_timeout=0.1)
    except Exception:
        logger.warning("Failed to create Redis client from %s", redis_url)
        return None


def _redis_get(client, key: str) -> Optional[Dict[str, Any]]:
    """Fetch and decode a JSON value from Redis.  Returns *None* on any error."""
    if client is None:
        return None
    try:
        raw = client.get(key)
        if raw is None:
            return None
        return json.loads(raw)
    except Exception:
        logger.warning("Redis GET failed for key=%s – bypassing cache", key)
        return None


def _redis_set(client, key: str, value: Dict[str, Any], ttl: int) -> None:
    """Store a JSON value in Redis with the given TTL.  Silently ignores errors."""
    if client is None:
        return
    try:
        client.setex(key, ttl, json.dumps(value))
    except Exception:
        logger.warning("Redis SET failed for key=%s – skipping cache store", key)


# ---------------------------------------------------------------------------
# Request handler
# ---------------------------------------------------------------------------

class CacheProxyHandler(BaseHTTPRequestHandler):
    """HTTP handler that proxies to vLLM with optional Redis caching."""

    # Set by the factory in ``make_handler``
    vllm_url: str = "http://localhost:8000"
    redis_url: str = "redis://localhost:6379"
    ttl: int = 3600
    _redis_client = None

    # Silence per-request log lines from BaseHTTPRequestHandler
    def log_message(self, fmt, *args):  # noqa: D401
        logger.debug(fmt, *args)

    # -- health endpoint -----------------------------------------------------

    def do_GET(self):  # noqa: N802
        if self.path == "/health":
            self._send_json(200, {"status": "ok"})
            return
        self._send_json(404, {"error": "not found"})

    # -- inference proxy -----------------------------------------------------

    def do_POST(self):  # noqa: N802
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length else b""

        # Parse the request body
        try:
            payload = json.loads(body) if body else {}
        except json.JSONDecodeError:
            self._send_json(400, {"error": "invalid JSON body"})
            return

        # Extract prompt text (OpenAI-compatible: messages or prompt field)
        prompt = self._extract_prompt(payload)

        # --- cache lookup ---------------------------------------------------
        cache_hit = False
        if prompt:
            cache_key = f"prefix:{compute_cache_key(prompt)}"
            cached = _redis_get(self._redis_client, cache_key)
            if cached is not None:
                cache_hit = True
                # Attach routing hint header so upstream LB can use it
                routing_hint = cached.get("routing_hint", "")
                logger.info("Cache HIT key=%s routing_hint=%s", cache_key, routing_hint)
        else:
            cache_key = None

        # --- forward to vLLM ------------------------------------------------
        forward_path = self.path if self.path else "/v1/completions"
        target_url = f"{self.vllm_url}{forward_path}"

        try:
            req = Request(
                target_url,
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urlopen(req, timeout=120) as resp:
                resp_body = resp.read()
                resp_status = resp.status
        except HTTPError as exc:
            resp_body = exc.read()
            resp_status = exc.code
        except (URLError, OSError) as exc:
            logger.error("Failed to reach vLLM at %s: %s", target_url, exc)
            self._send_json(502, {"error": "vLLM backend unavailable"})
            return

        # --- cache store on miss --------------------------------------------
        if prompt and not cache_hit and resp_status == 200 and cache_key:
            metadata = {
                "token_count": len(prompt.split()),
                "model": payload.get("model", "unknown"),
                "created_at": datetime.now(timezone.utc).isoformat(),
                "routing_hint": socket.gethostname(),
            }
            _redis_set(self._redis_client, cache_key, metadata, self.ttl)
            logger.info("Cache STORE key=%s", cache_key)

        # --- relay response -------------------------------------------------
        self.send_response(resp_status)
        self.send_header("Content-Type", "application/json")
        if cache_hit:
            self.send_header("X-Cache", "HIT")
            self.send_header("X-Routing-Hint", cached.get("routing_hint", ""))
        else:
            self.send_header("X-Cache", "MISS")
        self.end_headers()
        self.wfile.write(resp_body)

    # -- helpers -------------------------------------------------------------

    @staticmethod
    def _extract_prompt(payload: Dict[str, Any]) -> Optional[str]:
        """Pull the user prompt from an OpenAI-compatible request body."""
        # Chat completion style
        messages = payload.get("messages")
        if messages and isinstance(messages, list):
            for msg in reversed(messages):
                if msg.get("role") == "user":
                    return msg.get("content", "")
        # Text completion style
        prompt = payload.get("prompt")
        if isinstance(prompt, str):
            return prompt
        return None

    def _send_json(self, status: int, obj: Any) -> None:
        body = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def make_handler(vllm_url: str, redis_url: str, ttl: int):
    """Return a handler class pre-configured with runtime settings."""
    redis_client = _get_redis_client(redis_url)

    class _Handler(CacheProxyHandler):
        pass

    _Handler.vllm_url = vllm_url
    _Handler.redis_url = redis_url
    _Handler.ttl = ttl
    _Handler._redis_client = redis_client
    return _Handler


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------

def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Redis L3 cache proxy for vLLM")
    parser.add_argument("--listen-port", type=int, default=8080, help="Port to listen on (default: 8080)")
    parser.add_argument("--vllm-url", default="http://localhost:8000", help="vLLM backend URL (default: http://localhost:8000)")
    parser.add_argument("--redis-url", default="redis://localhost:6379", help="Redis URL (default: redis://localhost:6379)")
    parser.add_argument("--ttl", type=int, default=3600, help="Cache TTL in seconds (default: 3600)")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)

    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )

    handler_cls = make_handler(args.vllm_url, args.redis_url, args.ttl)
    server = HTTPServer(("0.0.0.0", args.listen_port), handler_cls)

    logger.info(
        "Cache proxy listening on :%d  vllm=%s  redis=%s  ttl=%ds",
        args.listen_port, args.vllm_url, args.redis_url, args.ttl,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Advanced vLLM inference client.

Supports ALB endpoints, LoRA adapters, JSON mode, guided JSON schemas,
and SSE streaming.  Automatically detects the loaded model name via
``/v1/models`` and falls back from chat completion to text completion
on 4xx errors.

Usage:
    python client.py --url http://localhost:8000 --prompt "Hello, world!"
    python client.py --url http://my-alb-dns --lora my-adapter --prompt "Summarize..."
    python client.py --json-mode --prompt "Extract entities from: ..."
    python client.py --schema schemas/entity-extraction.json --prompt "..."
    python client.py --streaming --prompt "Tell me a story"
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Dict, Optional
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError


# ---------------------------------------------------------------------------
# Pure helper – importable for property tests (Property 2)
# ---------------------------------------------------------------------------

def build_request_payload(
    model: str,
    prompt: str,
    lora: Optional[str] = None,
    json_mode: bool = False,
    schema: Optional[dict] = None,
) -> Dict[str, Any]:
    """Build an OpenAI-compatible chat completion request payload.

    Parameters
    ----------
    model:
        The base model name detected from ``/v1/models``.
    prompt:
        The user prompt text.
    lora:
        Optional LoRA adapter name.  When provided, the adapter name is
        used as the ``model`` field so vLLM routes to the correct adapter.
    json_mode:
        When *True*, adds ``response_format: {"type": "json_object"}``.
    schema:
        When provided, adds the schema dict under ``guided_json`` for
        vLLM's guided decoding.

    Returns
    -------
    dict
        A ready-to-serialize request payload.
    """
    payload: Dict[str, Any] = {
        "model": lora if lora else model,
        "messages": [{"role": "user", "content": prompt}],
    }

    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    if schema is not None:
        payload["guided_json"] = schema

    return payload


# ---------------------------------------------------------------------------
# Network helpers
# ---------------------------------------------------------------------------

def _json_request(url: str, method: str = "GET", data: Optional[bytes] = None) -> Any:
    """Send an HTTP request and return parsed JSON (or raise)."""
    req = Request(url, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    with urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def detect_model(base_url: str) -> str:
    """Query ``/v1/models`` and return the first model id."""
    resp = _json_request(f"{base_url}/v1/models")
    models = resp.get("data", [])
    if not models:
        raise RuntimeError("No models loaded on the server")
    return models[0]["id"]


def _stream_response(url: str, payload: bytes) -> None:
    """Send a streaming request and print SSE tokens to stdout."""
    req = Request(url, data=payload, method="POST")
    req.add_header("Content-Type", "application/json")
    with urlopen(req, timeout=120) as resp:
        for raw_line in resp:
            line = raw_line.decode("utf-8", errors="replace").strip()
            if not line or not line.startswith("data:"):
                continue
            data_str = line[len("data:"):].strip()
            if data_str == "[DONE]":
                break
            try:
                chunk = json.loads(data_str)
                # Chat completion streaming
                choices = chunk.get("choices", [])
                if choices:
                    delta = choices[0].get("delta", {})
                    token = delta.get("content", "")
                    if token:
                        print(token, end="", flush=True)
            except json.JSONDecodeError:
                continue
    # Final newline after streaming
    print()


def send_request(
    base_url: str,
    payload: Dict[str, Any],
    streaming: bool = False,
) -> None:
    """Send the inference request, falling back to text completion on 4xx."""
    chat_url = f"{base_url}/v1/chat/completions"

    if streaming:
        payload["stream"] = True

    body = json.dumps(payload).encode()

    # --- Try chat completion first ---
    try:
        if streaming:
            _stream_response(chat_url, body)
            return
        result = _json_request(chat_url, method="POST", data=body)
        _print_chat_result(result)
        return
    except HTTPError as exc:
        if 400 <= exc.code < 500:
            # Fall back to text completion
            pass
        else:
            _print_error(exc)
            return

    # --- Fallback: text completion ---
    completions_url = f"{base_url}/v1/completions"
    # Convert chat payload to text completion payload
    fallback_payload = dict(payload)
    messages = fallback_payload.pop("messages", [])
    prompt_text = " ".join(m.get("content", "") for m in messages if m.get("role") == "user")
    fallback_payload["prompt"] = prompt_text
    fallback_payload.pop("stream", None)

    fallback_body = json.dumps(fallback_payload).encode()
    try:
        if streaming:
            fallback_payload["stream"] = True
            _stream_response(completions_url, json.dumps(fallback_payload).encode())
            return
        result = _json_request(completions_url, method="POST", data=fallback_body)
        _print_completion_result(result)
    except HTTPError as exc:
        _print_error(exc)


def _print_chat_result(result: Dict[str, Any]) -> None:
    choices = result.get("choices", [])
    if choices:
        content = choices[0].get("message", {}).get("content", "")
        print(content)
    else:
        print(json.dumps(result, indent=2))


def _print_completion_result(result: Dict[str, Any]) -> None:
    choices = result.get("choices", [])
    if choices:
        print(choices[0].get("text", ""))
    else:
        print(json.dumps(result, indent=2))


def _print_error(exc: HTTPError) -> None:
    try:
        body = exc.read().decode("utf-8", errors="replace")
    except Exception:
        body = str(exc)
    print(f"Error {exc.code}: {body}", file=sys.stderr)


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------

def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Advanced vLLM inference client",
    )
    parser.add_argument(
        "--url",
        default="http://localhost:8000",
        help="vLLM server URL, e.g. ALB endpoint (default: http://localhost:8000)",
    )
    parser.add_argument(
        "--prompt",
        default="Explain what vLLM is in one sentence.",
        help="User prompt text",
    )
    parser.add_argument(
        "--lora",
        default=None,
        help="LoRA adapter name to use in the model field",
    )
    parser.add_argument(
        "--json-mode",
        action="store_true",
        help='Enable JSON mode (response_format: {"type": "json_object"})',
    )
    parser.add_argument(
        "--schema",
        default=None,
        help="Path to a JSON schema file for guided_json",
    )
    parser.add_argument(
        "--streaming",
        action="store_true",
        help="Enable SSE streaming responses",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)

    base_url = args.url.rstrip("/")

    # Load JSON schema if provided
    schema_dict = None
    if args.schema:
        try:
            with open(args.schema, "r") as f:
                schema_dict = json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            print(f"Error loading schema file: {exc}", file=sys.stderr)
            sys.exit(1)

    # Detect model name
    try:
        model_name = detect_model(base_url)
    except Exception as exc:
        print(f"Error detecting model: {exc}", file=sys.stderr)
        sys.exit(1)

    # Build payload
    payload = build_request_payload(
        model=model_name,
        prompt=args.prompt,
        lora=args.lora,
        json_mode=args.json_mode,
        schema=schema_dict,
    )

    # Send request
    try:
        send_request(base_url, payload, streaming=args.streaming)
    except (URLError, OSError) as exc:
        print(f"Connection error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

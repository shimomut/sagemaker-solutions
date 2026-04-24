#!/usr/bin/env python3
"""Client script for interacting with the vLLM OpenAI-compatible API server."""

import argparse
import sys

import requests


def get_model_name(base_url: str) -> str:
    """Query /v1/models and return the first loaded model name."""
    url = f"{base_url}/v1/models"
    resp = requests.get(url)
    if resp.status_code != 200:
        print(f"Error querying models: {resp.status_code}", file=sys.stderr)
        print(resp.text, file=sys.stderr)
        sys.exit(1)
    data = resp.json()
    model_name = data["data"][0]["id"]
    return model_name


def chat_completion(base_url: str, model: str, prompt: str) -> str:
    """Send a chat completion request and return the response text."""
    url = f"{base_url}/v1/chat/completions"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 256,
        "temperature": 0.7,
    }
    resp = requests.post(url, json=payload)
    if resp.status_code != 200:
        return None, resp
    data = resp.json()
    return data["choices"][0]["message"]["content"], resp


def completion(base_url: str, model: str, prompt: str) -> str:
    """Send a text completion request and return the response text."""
    url = f"{base_url}/v1/completions"
    payload = {
        "model": model,
        "prompt": prompt,
        "max_tokens": 256,
        "temperature": 0.7,
    }
    resp = requests.post(url, json=payload)
    if resp.status_code != 200:
        print(f"Error: {resp.status_code}", file=sys.stderr)
        print(resp.text, file=sys.stderr)
        sys.exit(1)
    data = resp.json()
    return data["choices"][0]["text"]


def main():
    parser = argparse.ArgumentParser(description="vLLM inference client")
    parser.add_argument(
        "--url",
        default="http://localhost:8000",
        help="vLLM server base URL (default: http://localhost:8000)",
    )
    parser.add_argument(
        "prompt",
        nargs="?",
        default="What is machine learning?",
        help="Prompt text (default: 'What is machine learning?')",
    )
    args = parser.parse_args()

    base_url = args.url.rstrip("/")

    print("Querying loaded model...")
    model_name = get_model_name(base_url)
    print(f"Model: {model_name}")

    # Try chat completion first (works with instruction-tuned models),
    # fall back to text completion for base models without a chat template.
    print("\nSending chat completion request...")
    response_text, resp = chat_completion(base_url, model_name, args.prompt)
    if response_text is not None:
        print(f"\nResponse:\n{response_text}")
    else:
        print("Chat completion not supported, falling back to text completion...")
        response_text = completion(base_url, model_name, args.prompt)
        print(f"\nResponse:\n{response_text}")


if __name__ == "__main__":
    main()

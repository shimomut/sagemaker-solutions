#!/usr/bin/env python3
"""vLLM inference benchmark tool.

Measures throughput, time-to-first-token (TTFT), end-to-end latency
(P50/P95/P99), and inter-token latency (ITL) under configurable
concurrency.  Supports ``--compare`` mode for side-by-side comparison
and ``--output json`` for machine-readable results.

Usage:
    python benchmark.py --url http://localhost:8000 --concurrency 4 --num-requests 50
    python benchmark.py --url http://localhost:8000 --output json
    python benchmark.py --compare http://url-a http://url-b --concurrency 8
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import sys
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple


# ---------------------------------------------------------------------------
# Pure helpers – importable for property tests (Property 3 & 4)
# ---------------------------------------------------------------------------

def compute_percentiles(
    values: Sequence[float],
    percentiles: Tuple[int, ...] = (50, 95, 99),
) -> Dict[int, float]:
    """Compute percentiles from a list of numeric values.

    Uses the *nearest-rank* method: for percentile *p* the index is
    ``ceil(p / 100 * n) - 1`` clamped to ``[0, n-1]``.

    Parameters
    ----------
    values:
        Non-empty sequence of floats.
    percentiles:
        Tuple of integer percentile values (e.g. 50, 95, 99).

    Returns
    -------
    dict
        Mapping from percentile int to the computed float value.

    Raises
    ------
    ValueError
        If *values* is empty.
    """
    if not values:
        raise ValueError("values must be non-empty")
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    result: Dict[int, float] = {}
    for p in percentiles:
        idx = max(0, min(math.ceil(p / 100.0 * n) - 1, n - 1))
        result[p] = sorted_vals[idx]
    return result


def serialize_results(results_dict: Dict[str, Any]) -> str:
    """Serialize benchmark results to a JSON string.

    Parameters
    ----------
    results_dict:
        A benchmark results dict matching the output schema (with
        ``config`` and ``results`` keys).

    Returns
    -------
    str
        JSON string representation.
    """
    return json.dumps(results_dict, indent=2, sort_keys=True)


def deserialize_results(json_str: str) -> Dict[str, Any]:
    """Deserialize a JSON string back to a benchmark results dict.

    Parameters
    ----------
    json_str:
        JSON string previously produced by :func:`serialize_results`.

    Returns
    -------
    dict
        The reconstructed results dict.
    """
    return json.loads(json_str)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

class RequestResult:
    """Holds timing data for a single benchmark request."""

    __slots__ = (
        "success",
        "ttft_ms",
        "latency_ms",
        "token_count",
        "inter_token_latencies_ms",
        "error",
    )

    def __init__(
        self,
        success: bool = False,
        ttft_ms: float = 0.0,
        latency_ms: float = 0.0,
        token_count: int = 0,
        inter_token_latencies_ms: Optional[List[float]] = None,
        error: Optional[str] = None,
    ):
        self.success = success
        self.ttft_ms = ttft_ms
        self.latency_ms = latency_ms
        self.token_count = token_count
        self.inter_token_latencies_ms = inter_token_latencies_ms or []
        self.error = error


# ---------------------------------------------------------------------------
# Async benchmark engine
# ---------------------------------------------------------------------------

async def _send_one_request(
    session: Any,
    url: str,
    payload: Dict[str, Any],
    timeout: float,
) -> RequestResult:
    """Send a single streaming request and collect timing data."""
    import aiohttp

    chat_url = f"{url}/v1/chat/completions"
    body = payload.copy()
    body["stream"] = True

    start = time.perf_counter()
    first_token_time: Optional[float] = None
    token_times: List[float] = []
    token_count = 0

    try:
        async with session.post(
            chat_url,
            json=body,
            timeout=aiohttp.ClientTimeout(total=timeout),
        ) as resp:
            if resp.status >= 400:
                text = await resp.text()
                return RequestResult(
                    success=False,
                    latency_ms=(time.perf_counter() - start) * 1000,
                    error=f"HTTP {resp.status}: {text[:200]}",
                )

            async for raw_line in resp.content:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line or not line.startswith("data:"):
                    continue
                data_str = line[len("data:"):].strip()
                if data_str == "[DONE]":
                    break
                try:
                    chunk = json.loads(data_str)
                    choices = chunk.get("choices", [])
                    if choices:
                        delta = choices[0].get("delta", {})
                        if delta.get("content"):
                            now = time.perf_counter()
                            if first_token_time is None:
                                first_token_time = now
                            token_times.append(now)
                            token_count += 1
                except json.JSONDecodeError:
                    continue

    except asyncio.TimeoutError:
        return RequestResult(
            success=False,
            latency_ms=(time.perf_counter() - start) * 1000,
            error="Timeout",
        )
    except Exception as exc:
        return RequestResult(
            success=False,
            latency_ms=(time.perf_counter() - start) * 1000,
            error=str(exc),
        )

    end = time.perf_counter()
    latency_ms = (end - start) * 1000
    ttft_ms = ((first_token_time - start) * 1000) if first_token_time else latency_ms

    # Inter-token latencies
    itl_list: List[float] = []
    for i in range(1, len(token_times)):
        itl_list.append((token_times[i] - token_times[i - 1]) * 1000)

    return RequestResult(
        success=True,
        ttft_ms=ttft_ms,
        latency_ms=latency_ms,
        token_count=token_count,
        inter_token_latencies_ms=itl_list,
    )


async def run_benchmark(
    url: str,
    concurrency: int,
    num_requests: int,
    prompt: str,
    timeout: float,
) -> Dict[str, Any]:
    """Run the benchmark and return a results dict matching the output schema."""
    import aiohttp

    payload = {
        "model": "default",
        "messages": [{"role": "user", "content": prompt}],
    }

    # Try to detect the model name
    try:
        async with aiohttp.ClientSession() as sess:
            async with sess.get(
                f"{url}/v1/models",
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    models = data.get("data", [])
                    if models:
                        payload["model"] = models[0]["id"]
    except Exception:
        pass  # Use "default" as model name

    sem = asyncio.Semaphore(concurrency)
    results: List[RequestResult] = []

    async def _worker() -> RequestResult:
        async with sem:
            async with aiohttp.ClientSession() as sess:
                return await _send_one_request(sess, url, payload, timeout)

    overall_start = time.perf_counter()
    tasks = [asyncio.create_task(_worker()) for _ in range(num_requests)]
    results = await asyncio.gather(*tasks)
    overall_end = time.perf_counter()

    total_duration = overall_end - overall_start

    # Aggregate
    successful = [r for r in results if r.success]
    failed = [r for r in results if not r.success]

    latencies = [r.latency_ms for r in successful]
    ttfts = [r.ttft_ms for r in successful]
    total_tokens = sum(r.token_count for r in successful)
    all_itls: List[float] = []
    for r in successful:
        all_itls.extend(r.inter_token_latencies_ms)

    pcts = compute_percentiles(latencies) if latencies else {50: 0.0, 95: 0.0, 99: 0.0}
    avg_ttft = (sum(ttfts) / len(ttfts)) if ttfts else 0.0
    avg_itl = (sum(all_itls) / len(all_itls)) if all_itls else 0.0
    throughput = total_tokens / total_duration if total_duration > 0 else 0.0

    return {
        "config": {
            "url": url,
            "concurrency": concurrency,
            "num_requests": num_requests,
            "prompt": prompt,
        },
        "results": {
            "throughput_tokens_per_sec": round(throughput, 2),
            "avg_ttft_ms": round(avg_ttft, 2),
            "p50_latency_ms": round(pcts[50], 2),
            "p95_latency_ms": round(pcts[95], 2),
            "p99_latency_ms": round(pcts[99], 2),
            "avg_itl_ms": round(avg_itl, 2),
            "total_duration_sec": round(total_duration, 2),
            "successful_requests": len(successful),
            "failed_requests": len(failed),
        },
    }


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------

def _format_table(data: Dict[str, Any], label: str = "") -> str:
    """Format benchmark results as a human-readable table."""
    cfg = data["config"]
    res = data["results"]
    header = f" Benchmark Results{f' ({label})' if label else ''} "
    lines = [
        f"{'=' * 55}",
        f"{header:^55}",
        f"{'=' * 55}",
        f"  URL:                  {cfg['url']}",
        f"  Concurrency:          {cfg['concurrency']}",
        f"  Total Requests:       {cfg['num_requests']}",
        f"  Successful:           {res['successful_requests']}",
        f"  Failed:               {res['failed_requests']}",
        f"{'-' * 55}",
        f"  Throughput:           {res['throughput_tokens_per_sec']:>10.2f} tokens/s",
        f"  Avg TTFT:             {res['avg_ttft_ms']:>10.2f} ms",
        f"  P50 Latency:          {res['p50_latency_ms']:>10.2f} ms",
        f"  P95 Latency:          {res['p95_latency_ms']:>10.2f} ms",
        f"  P99 Latency:          {res['p99_latency_ms']:>10.2f} ms",
        f"  Avg ITL:              {res['avg_itl_ms']:>10.2f} ms",
        f"  Total Duration:       {res['total_duration_sec']:>10.2f} s",
        f"{'=' * 55}",
    ]
    return "\n".join(lines)


def _format_compare_table(data_a: Dict[str, Any], data_b: Dict[str, Any]) -> str:
    """Format two benchmark results as a side-by-side comparison table."""
    res_a = data_a["results"]
    res_b = data_b["results"]
    url_a = data_a["config"]["url"]
    url_b = data_b["config"]["url"]

    metrics = [
        ("Throughput (tok/s)", "throughput_tokens_per_sec"),
        ("Avg TTFT (ms)", "avg_ttft_ms"),
        ("P50 Latency (ms)", "p50_latency_ms"),
        ("P95 Latency (ms)", "p95_latency_ms"),
        ("P99 Latency (ms)", "p99_latency_ms"),
        ("Avg ITL (ms)", "avg_itl_ms"),
        ("Duration (s)", "total_duration_sec"),
        ("Successful", "successful_requests"),
        ("Failed", "failed_requests"),
    ]

    col_w = 15
    label_w = 22
    lines = [
        f"{'=' * (label_w + col_w * 2 + 7)}",
        f"{'Metric':<{label_w}} | {'Config A':>{col_w}} | {'Config B':>{col_w}}",
        f"{'-' * (label_w + col_w * 2 + 7)}",
    ]
    for label, key in metrics:
        va = res_a.get(key, 0)
        vb = res_b.get(key, 0)
        lines.append(f"  {label:<{label_w - 2}} | {va:>{col_w}.2f} | {vb:>{col_w}.2f}")
    lines.append(f"{'-' * (label_w + col_w * 2 + 7)}")
    lines.append(f"  Config A: {url_a}")
    lines.append(f"  Config B: {url_b}")
    lines.append(f"{'=' * (label_w + col_w * 2 + 7)}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------

def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="vLLM inference benchmark tool",
    )
    parser.add_argument(
        "--url",
        default="http://localhost:8000",
        help="vLLM server URL (default: http://localhost:8000)",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=4,
        help="Number of concurrent requests (default: 4)",
    )
    parser.add_argument(
        "--num-requests",
        type=int,
        default=20,
        help="Total number of requests to send (default: 20)",
    )
    parser.add_argument(
        "--prompt",
        default="Explain what vLLM is in one paragraph.",
        help="Prompt text for benchmark requests",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=120.0,
        help="Per-request timeout in seconds (default: 120)",
    )
    parser.add_argument(
        "--output",
        choices=["table", "json"],
        default="table",
        help="Output format: table (default) or json",
    )
    parser.add_argument(
        "--compare",
        nargs=2,
        metavar=("URL_A", "URL_B"),
        default=None,
        help="Compare mode: run same workload against two URLs",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)

    if args.compare:
        url_a, url_b = args.compare
        print(f"Running benchmark against Config A: {url_a}", file=sys.stderr)
        data_a = asyncio.run(run_benchmark(
            url=url_a,
            concurrency=args.concurrency,
            num_requests=args.num_requests,
            prompt=args.prompt,
            timeout=args.timeout,
        ))
        print(f"Running benchmark against Config B: {url_b}", file=sys.stderr)
        data_b = asyncio.run(run_benchmark(
            url=url_b,
            concurrency=args.concurrency,
            num_requests=args.num_requests,
            prompt=args.prompt,
            timeout=args.timeout,
        ))

        if args.output == "json":
            combined = {"config_a": data_a, "config_b": data_b}
            print(serialize_results(combined))
        else:
            print(_format_compare_table(data_a, data_b))
    else:
        data = asyncio.run(run_benchmark(
            url=args.url,
            concurrency=args.concurrency,
            num_requests=args.num_requests,
            prompt=args.prompt,
            timeout=args.timeout,
        ))

        if args.output == "json":
            print(serialize_results(data))
        else:
            print(_format_table(data))


if __name__ == "__main__":
    main()

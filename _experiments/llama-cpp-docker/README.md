# llama.cpp in Docker on MacBook (CPU)

An experimental sandbox for learning [llama.cpp](https://github.com/ggml-org/llama.cpp) without installing anything on the host. Uses the official `ghcr.io/ggml-org/llama.cpp` images and bind-mounts a local `models/` directory for GGUF files.

## Why Docker (and the caveat)

Running llama.cpp in a container on macOS keeps the host clean, which is the whole point here. The tradeoff is that Docker Desktop runs containers inside a Linux VM with no access to the Mac's GPU, so **Metal acceleration is unavailable and inference runs on CPU only**. That's fine for learning the project, trying out prompts, quantizations, and the HTTP server, but it will be noticeably slower than a native `brew install llama.cpp` build.

If performance becomes the bottleneck, switch to a native build later.

## Prerequisites

- Docker Desktop for Mac, running
- Enough memory allocated to Docker (Settings → Resources). 6–8 GB is a comfortable starting point for 1B–3B models at Q4.
- An internet connection for the first model download (~1 GB with defaults)

## Quickstart

```bash
# 1. Pull the images
make pull

# 2. Download the default model (Qwen2.5 1.5B Instruct, Q4_K_M, ~1 GB)
make download-model

# 3. Start an interactive chat in the terminal
make cli
```

Type messages, hit Enter, `Ctrl+C` to exit.

## HTTP server mode

llama.cpp ships an OpenAI-compatible server. Handy if you want to poke at it from another tool or from Python/curl.

```bash
# Run in the foreground (Ctrl+C to stop)
make server

# Or run detached
make server-bg
make logs          # follow logs
make chat          # send a test chat completion
make stop          # shut it down
```

Once running, the built-in web UI is at <http://localhost:8080>, and the OpenAI-style endpoint is `http://localhost:8080/v1/chat/completions`.

## Swapping models

Override the make variables to try a different GGUF. Any Hugging Face repo with a `.gguf` asset works.

```bash
# Smaller + faster (0.5B)
make download-model \
    MODEL_REPO=Qwen/Qwen2.5-0.5B-Instruct-GGUF \
    MODEL_FILE=qwen2.5-0.5b-instruct-q4_k_m.gguf

make cli \
    MODEL_FILE=qwen2.5-0.5b-instruct-q4_k_m.gguf
```

Quantization guide for a MacBook Air on CPU:

| Quant    | Size (1.5B) | Speed | Quality |
|----------|-------------|-------|---------|
| Q4_K_M   | ~1 GB       | fast  | good    |
| Q5_K_M   | ~1.2 GB     | ~20% slower | better  |
| Q8_0     | ~1.8 GB     | slow  | near-FP16 |
| F16      | ~3 GB       | slowest | reference |

Stick to Q4_K_M or Q5_K_M for anything larger than ~3B unless you enjoy waiting.

## Performance knobs

In the `Makefile`:

- `THREADS`   — passed as `-t`. Set to the number of physical cores you want to give the container (e.g. 4 on an M1 Air).
- `CTX_SIZE`  — passed as `-c`. Context window. Larger uses more RAM.
- `HOST_PORT` — host port for the server (default 8080).

Example:

```bash
make server-bg THREADS=8 CTX_SIZE=8192 HOST_PORT=9090
```

## What to explore

- **Interactive vs instruct prompting**: compare `-cnv` (conversation mode, default here) with plain completion (`make cli` with your own args).
- **Quantization impact**: download Q4_K_M and Q8_0 of the same model, compare speed and output quality.
- **Server parameters**: visit the web UI at <http://localhost:8080>, tweak `temperature`, `top_k`, `top_p`, repeat penalty, watch outputs change.
- **OpenAI compatibility**: point any OpenAI SDK at `http://localhost:8080/v1` with a dummy API key and it just works.
- **Grammar / JSON mode**: llama.cpp supports GBNF grammars to force structured output. Try the `--grammar-file` flag.

## Cleanup

```bash
make clean       # remove the running/stopped server container
make distclean   # also delete downloaded models
```

## Layout

```
llama-cpp-docker/
├── Makefile          # all the commands above
├── README.md         # this file
├── .gitignore        # excludes models/ from git
└── models/           # created on first download, git-ignored
```

No Python dependencies, no Dockerfile to build; the official images do all the work.

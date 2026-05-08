# llama.cpp on MacBook via Docker (CPU only)
#
# Notes
# - Docker Desktop on macOS runs containers in a Linux VM and has no GPU passthrough,
#   so this setup is CPU-only. Metal acceleration requires a native build (e.g. brew).
# - Models are stored in ./models/ and bind-mounted into the container at /models.

# --- Configuration ---------------------------------------------------------

# Pin a specific image digest in real projects; for an experiment :full / :server is fine.
IMAGE_FULL    ?= ghcr.io/ggml-org/llama.cpp:full
IMAGE_SERVER  ?= ghcr.io/ggml-org/llama.cpp:server

# Default model: Qwen2.5 1.5B Instruct, Q4_K_M quantization (~1 GB).
# Small enough to run at reasonable speed on CPU inside a MacBook Air VM.
MODEL_REPO  ?= Qwen/Qwen2.5-1.5B-Instruct-GGUF
MODEL_FILE  ?= qwen2.5-1.5b-instruct-q4_k_m.gguf
MODEL_URL   ?= https://huggingface.co/$(MODEL_REPO)/resolve/main/$(MODEL_FILE)

MODELS_DIR  := $(abspath models)
HOST_PORT   ?= 8080

# Runtime tuning. Adjust -t to the number of CPU cores you want the container to use.
THREADS     ?= 4
CTX_SIZE    ?= 4096

CONTAINER_NAME := llama-cpp-server

# --- Targets ---------------------------------------------------------------

.PHONY: help pull download-model cli server server-bg logs stop chat clean distclean

help:
	@echo "llama.cpp in Docker (CPU) — common targets"
	@echo ""
	@echo "  make pull            Pull llama.cpp images ($(IMAGE_FULL), $(IMAGE_SERVER))"
	@echo "  make download-model  Download $(MODEL_FILE) into ./models/"
	@echo "  make cli             Interactive llama-cli session (Ctrl+C to exit)"
	@echo "  make server          Run llama-server in the foreground on :$(HOST_PORT)"
	@echo "  make server-bg       Run llama-server detached (container: $(CONTAINER_NAME))"
	@echo "  make logs            Tail logs of the background server"
	@echo "  make stop            Stop the background server"
	@echo "  make chat            Send a test chat completion to the server"
	@echo "  make clean           Remove the background container"
	@echo "  make distclean       Remove container AND downloaded models"
	@echo ""
	@echo "Override variables on the command line, e.g.:"
	@echo "  make download-model MODEL_REPO=Qwen/Qwen2.5-0.5B-Instruct-GGUF \\"
	@echo "                      MODEL_FILE=qwen2.5-0.5b-instruct-q4_k_m.gguf"

$(MODELS_DIR):
	mkdir -p $(MODELS_DIR)

pull:
	docker pull $(IMAGE_FULL)
	docker pull $(IMAGE_SERVER)

download-model: $(MODELS_DIR)
	@if [ -f "$(MODELS_DIR)/$(MODEL_FILE)" ]; then \
		echo "Model already present: $(MODELS_DIR)/$(MODEL_FILE)"; \
	else \
		echo "Downloading $(MODEL_URL)"; \
		curl -L --fail -o "$(MODELS_DIR)/$(MODEL_FILE)" "$(MODEL_URL)"; \
	fi

cli: download-model
	docker run --rm -it \
		--entrypoint /app/llama-cli \
		-v $(MODELS_DIR):/models \
		$(IMAGE_FULL) \
		-m /models/$(MODEL_FILE) \
		-t $(THREADS) \
		-c $(CTX_SIZE) \
		-cnv

server: download-model
	docker run --rm -it \
		--name $(CONTAINER_NAME) \
		-v $(MODELS_DIR):/models \
		-p $(HOST_PORT):8080 \
		$(IMAGE_SERVER) \
		-m /models/$(MODEL_FILE) \
		-t $(THREADS) \
		-c $(CTX_SIZE) \
		--host 0.0.0.0 --port 8080

server-bg: download-model
	docker run -d --rm \
		--name $(CONTAINER_NAME) \
		-v $(MODELS_DIR):/models \
		-p $(HOST_PORT):8080 \
		$(IMAGE_SERVER) \
		-m /models/$(MODEL_FILE) \
		-t $(THREADS) \
		-c $(CTX_SIZE) \
		--host 0.0.0.0 --port 8080
	@echo "Server starting on http://localhost:$(HOST_PORT)"
	@echo "Tail logs with:  make logs"
	@echo "Stop it with:    make stop"

logs:
	docker logs -f $(CONTAINER_NAME)

stop:
	-docker stop $(CONTAINER_NAME)

chat:
	@curl -sS http://localhost:$(HOST_PORT)/v1/chat/completions \
		-H "Content-Type: application/json" \
		-d '{"messages":[{"role":"user","content":"In one sentence, what is llama.cpp?"}]}' \
		| python3 -m json.tool

clean:
	-docker rm -f $(CONTAINER_NAME) 2>/dev/null || true

distclean: clean
	rm -rf $(MODELS_DIR)

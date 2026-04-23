# HyperPod EKS vLLM

Run vLLM inference on a SageMaker HyperPod EKS cluster. This project demonstrates:

- Building a custom Docker image with vLLM on an NVIDIA CUDA base
- Deploying vLLM as a Kubernetes workload with GPU scheduling
- Serving models from Hugging Face Hub via the OpenAI-compatible API
- Interacting with the server using a Python client script

The default configuration serves `facebook/opt-1.3b` on a single GPU. Models are downloaded at runtime from Hugging Face Hub, so switching models only requires editing the Kubernetes manifest and redeploying — no image rebuild needed.

## Prerequisites

- **kubectl** configured for your HyperPod EKS cluster
- **Docker** for building the container image
- **AWS CLI** configured with permissions to push to ECR
- **GPU nodes** available on the HyperPod EKS cluster (at least one node with an NVIDIA GPU)
- **Python 3** with `requests` installed (`pip install -r requirements.txt`) for the client script

## Build and Push

1. Build the Docker image:

   ```bash
   make build
   ```

2. Log in to ECR:

   ```bash
   make login
   ```

3. Tag and push the image:

   ```bash
   make tag
   make push
   ```

   This pushes to `842413447717.dkr.ecr.us-west-2.amazonaws.com/hyperpod-eks-vllm:latest`.

## Deploy

Apply the Kubernetes deployment and service:

```bash
make deploy
```

Check that the pod is running:

```bash
make list-pods
```

The vLLM server downloads the model on first startup, which may take a few minutes. Monitor progress with:

```bash
make watch-logs
```

To remove the deployment:

```bash
make delete
```

## Port Forward

Forward the vLLM server port to your local machine:

```bash
make port-forward
```

This runs `kubectl port-forward svc/vllm-server 8000:8000`, making the API available at `http://localhost:8000`. Keep this running in a separate terminal.

## Client Usage

Set up the Python virtual environment (one-time):

```bash
make venv
```

With port-forwarding active, run the client script:

```bash
make test-inference
```

Pass a custom prompt:

```bash
make test-inference PROMPT="Explain transformers in deep learning"
```

The client automatically detects the API mode:
- For instruction-tuned models (e.g., Mistral, Llama), it uses `/v1/chat/completions` which produces focused, conversational answers.
- For base models without a chat template (e.g., `facebook/opt-1.3b`), it falls back to `/v1/completions` (text completion).

You can also run the client directly:

```bash
.venv/bin/python client.py "Your prompt here"
.venv/bin/python client.py --url http://localhost:8000 "Your prompt here"
```

## Configuration

Key vLLM arguments are configured in `deployment.yaml` under the container `args` section:

| Argument | Description | Default |
|----------|-------------|---------|
| `--model` | Model identifier from Hugging Face Hub (e.g., `facebook/opt-1.3b`) | `facebook/opt-1.3b` |
| `--tensor-parallel-size` | Number of GPUs for tensor parallelism. Increase for larger models that don't fit on a single GPU. | `1` |
| `--gpu-memory-utilization` | Fraction of GPU memory vLLM is allowed to use (0.0–1.0). Lower this if you encounter OOM errors. | `0.9` |

To change a setting, edit the corresponding value in `deployment.yaml` and redeploy:

```bash
make deploy
```

## Recommended Models

| Model | Approx. GPU Memory | GPUs | Notes |
|-------|-------------------|------|-------|
| `facebook/opt-1.3b` | ~3 GB | 1 | Open model, no authentication required. Good for quick testing. |
| `mistralai/Mistral-7B-Instruct-v0.3` | ~15 GB | 1 | Instruction-tuned, strong general performance. |
| `meta-llama/Llama-3.1-8B-Instruct` | ~17 GB | 1 | Gated model, requires Hugging Face token. See [Hugging Face Authentication](#hugging-face-authentication). |

GPU memory estimates are approximate and depend on context length and batch size. If you encounter out-of-memory errors, try lowering `--gpu-memory-utilization` or switching to a smaller model.

## Switching Models

The `deployment.yaml` has pre-configured model options. To switch, comment/uncomment the desired model line:

```yaml
args:
  - "--model"
  ## --- Pick one model (uncomment one line) ---
  #- "facebook/opt-1.3b"              # ~3 GB, no auth required
  - "mistralai/Mistral-7B-Instruct-v0.3"  # ~15 GB, supports chat
  #- "meta-llama/Llama-3.1-8B-Instruct"    # ~17 GB, requires HF token
  ## -------------------------------------------
```

Then redeploy:

```bash
make deploy
```

If the model requires multiple GPUs, also update `--tensor-parallel-size` and the GPU resource limit:

```yaml
args:
  - "--tensor-parallel-size"
  - "2"
```

```yaml
resources:
  limits:
    nvidia.com/gpu: 2
```

Monitor startup and model download progress:

```bash
make watch-logs
```

The new model is downloaded from Hugging Face Hub on startup. Download time depends on model size and network speed.

## Hugging Face Authentication

Some models (e.g., `meta-llama/Llama-3.1-8B-Instruct`) are gated — you must accept the license on the model's Hugging Face page and provide an access token. Open models like `facebook/opt-1.3b` and `mistralai/Mistral-7B-Instruct-v0.3` don't require a token.

To use a gated model:

1. Accept the model license on its Hugging Face page.

2. Create an access token at [https://huggingface.co/settings/tokens](https://huggingface.co/settings/tokens).

3. Set the token in `deployment.yaml`:

   ```yaml
   env:
     - name: HUGGING_FACE_HUB_TOKEN
       value: "hf_your_token_here"
   ```

4. Redeploy:

   ```bash
   make deploy
   ```

> **Tip:** Avoid committing your Hugging Face token to version control. For production use, store the token in a Kubernetes Secret and reference it via `secretKeyRef` in the deployment manifest.

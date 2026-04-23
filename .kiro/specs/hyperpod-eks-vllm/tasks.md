# Implementation Plan: HyperPod EKS vLLM

## Overview

Build a learning-focused experimental project under `_experiments/hyperpod_eks_vllm` that demonstrates running vLLM inference on a HyperPod EKS cluster. The implementation follows the repository's standard project layout and proceeds incrementally: project scaffolding → Dockerfile → Kubernetes manifest → Makefile → client script → documentation.

## Tasks

- [x] 1. Set up project structure and supporting files
  - Create the `_experiments/hyperpod_eks_vllm` directory
  - Create `.gitignore` excluding `__pycache__/`, `*.pyc`, `.venv/`, `.DS_Store`
  - Create `requirements.txt` containing `requests`
  - _Requirements: 1.1, 1.3_

- [x] 2. Create the Dockerfile
  - Use `nvidia/cuda:12.4.1-devel-ubuntu22.04` as the base image
  - Install Python 3.10 via apt
  - Install vLLM via pip
  - Set entrypoint to `python -m vllm.entrypoints.openai.api_server`
  - Expose port 8000
  - _Requirements: 2.1, 2.2_

- [x] 3. Create the Kubernetes deployment manifest
  - [x] 3.1 Define the Deployment resource in `deployment.yaml`
    - Set label `app: vllm-server` and 1 replica
    - Request `nvidia.com/gpu: 1` resource
    - Add toleration for `nvidia.com/gpu` taint (Exists/NoSchedule)
    - Mount emptyDir with `medium: Memory` at `/dev/shm`
    - Configure container args: `--model`, `--tensor-parallel-size`, `--gpu-memory-utilization`, `--host 0.0.0.0`, `--port 8000`
    - Set default model to `facebook/opt-1.3b`, tensor parallelism to `1`, GPU memory utilization to `0.9`
    - Add `HUGGING_FACE_HUB_TOKEN` environment variable from optional env var
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.6, 6.1, 6.2, 6.3, 6.4, 7.1, 7.2, 7.6_
  - [x] 3.2 Define the Service resource in `deployment.yaml`
    - Type ClusterIP, port 8000 → 8000, selector `app: vllm-server`
    - _Requirements: 3.5_

- [x] 4. Create the Makefile
  - Add `build` target: `docker build --tag hyperpod-eks-vllm .`
  - Add `login` target: `aws ecr get-login-password` piped to `docker login`
  - Add `tag` target: tag image for ECR path `842413447717.dkr.ecr.us-west-2.amazonaws.com/hyperpod-eks-vllm:latest`
  - Add `push` target: push tagged image to ECR
  - Add `deploy` target: `kubectl apply -f deployment.yaml`
  - Add `delete` target: `kubectl delete -f deployment.yaml`
  - Add `list-pods` target: `kubectl get pods -l app=vllm-server -o wide`
  - Add `watch-logs` target: `kubectl logs -f -l app=vllm-server`
  - Add `port-forward` target: `kubectl port-forward svc/vllm-server 8000:8000`
  - _Requirements: 1.2, 2.3, 2.4, 2.5, 3.7_

- [x] 5. Checkpoint - Verify project structure
  - Ensure all files exist: `.gitignore`, `requirements.txt`, `Dockerfile`, `deployment.yaml`, `Makefile`
  - Ensure Makefile has all required targets: `build`, `login`, `tag`, `push`, `deploy`, `delete`, `list-pods`, `watch-logs`
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Create the client script
  - [x] 6.1 Implement `client.py` with argparse accepting `--url` (default `http://localhost:8000`)
    - Query `/v1/models` endpoint and print the currently loaded model name
    - Send a chat completion request to `/v1/chat/completions` with a sample prompt
    - Print the model response text to stdout
    - On HTTP errors, print status code and response body to stderr
    - Use only the `requests` library for HTTP communication
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 7.8_

- [x] 7. Create the README.md documentation
  - [x] 7.1 Write overview, prerequisites, and build/deploy sections
    - Overview describing project purpose and vLLM features demonstrated
    - Prerequisites listing kubectl, Docker, AWS CLI, and GPU node requirements
    - Step-by-step build, ECR push, and deploy instructions
    - _Requirements: 5.1, 5.2, 5.3_
  - [x] 7.2 Write port-forward, client usage, and configuration sections
    - Instructions for `kubectl port-forward` to access vLLM server locally
    - Example of running `client.py` to send a chat completion request
    - vLLM configuration options section (model selection, tensor parallelism, GPU memory utilization)
    - _Requirements: 5.4, 5.5, 5.6_
  - [x] 7.3 Write model switching and Hugging Face authentication sections
    - Recommended models table with at least three models (`facebook/opt-1.3b`, `mistralai/Mistral-7B-Instruct-v0.3`, `meta-llama/Llama-3.1-8B-Instruct`) and approximate GPU memory requirements
    - Step-by-step instructions for switching models by editing the manifest and redeploying
    - Instructions for passing a Hugging Face access token for gated models
    - _Requirements: 7.3, 7.4, 7.5, 7.6_

- [x] 8. Final checkpoint - Review all files
  - Verify all seven files exist in `_experiments/hyperpod_eks_vllm`: README.md, Makefile, Dockerfile, deployment.yaml, client.py, requirements.txt, .gitignore
  - Verify requirements coverage across all files
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- No automated tests are needed — this is a learning-focused project with manual smoke testing
- No property-based testing applies (infrastructure config + thin HTTP client)
- All vLLM configuration is passed via container command args in the K8s manifest, not baked into the Docker image
- Model weights are downloaded at runtime from Hugging Face Hub, keeping the image small and model-agnostic

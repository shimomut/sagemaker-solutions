# Implementation Plan: Advanced vLLM Inference on HyperPod EKS

## Overview

Build a modular, production-grade vLLM inference showcase project at `hyperpod_eks_vllm_advanced/`. The implementation proceeds incrementally: rename the basic experiment → scaffold the advanced project → create the Dockerfile and base manifests → add per-feature manifests → implement Python scripts (cache proxy, client, benchmark) → wire everything together via Makefile → write comprehensive documentation. Each task builds on the previous, and every manifest/script is integrated into the Makefile before moving on.

## Tasks

- [ ] 1. Rename basic experiment and scaffold advanced project
  - [ ] 1.1 Move `_experiments/hyperpod_eks_vllm` to `hyperpod_eks_vllm_basic`
    - Move the entire directory to the top-level as `hyperpod_eks_vllm_basic`
    - Update the basic project's README.md to reference `hyperpod_eks_vllm_advanced` as the next step for learning advanced techniques
    - _Requirements: 1.2, 1.9_
  - [ ] 1.2 Create the `hyperpod_eks_vllm_advanced` project structure
    - Create the top-level directory `hyperpod_eks_vllm_advanced/`
    - Create `manifests/` subdirectory for Kubernetes YAML files
    - Create `schemas/` subdirectory for JSON schema examples
    - Create `.gitignore` excluding `__pycache__/`, `*.pyc`, `.venv/`, `.env`, `.DS_Store`, `*.egg-info/`
    - Create `requirements.txt` with pinned versions: `vllm`, `ray[default]`, `redis`, `aiohttp`, `requests`, `hypothesis` (for testing)
    - _Requirements: 1.1, 1.3, 1.4, 1.5, 1.8_

- [ ] 2. Create the Dockerfile
  - Use `nvidia/cuda:12.4.1-devel-ubuntu22.04` as the base image
  - Install Python 3.10 via apt
  - Install vLLM with Ray support, redis-py, and aiohttp from `requirements.txt`
  - Expose port 8000
  - Set entrypoint to `["vllm", "serve"]`
  - _Requirements: 19.1, 19.2, 19.3, 19.4_

- [ ] 3. Create base vLLM deployment and service manifests
  - [ ] 3.1 Create `manifests/vllm-deployment.yaml`
    - Define Deployment with label `app: vllm-advanced-server`, component `vllm`, part-of `hyperpod-eks-vllm-advanced`
    - Set image to `842413447717.dkr.ecr.us-west-2.amazonaws.com/hyperpod-eks-vllm-advanced:latest`
    - Configure container args with default model `meta-llama/Llama-3.1-8B-Instruct`, `--tensor-parallel-size 1`, `--gpu-memory-utilization 0.9`, `--host 0.0.0.0`, `--port 8000`
    - Add clearly commented arg blocks for each feature: prefix caching, chunked prefill, speculative decoding, LoRA adapters, FP8 quantization, pipeline parallelism
    - Request `nvidia.com/gpu: 1` (configurable), mount `/dev/shm` emptyDir with Memory medium
    - Add readiness probe on `/health` endpoint
    - Add `HUGGING_FACE_HUB_TOKEN` env var from optional secret
    - Add GPU toleration for `nvidia.com/gpu`
    - _Requirements: 2.1, 2.4, 3.1, 3.2, 3.3, 3.5, 7.1, 7.5, 8.1, 10.1, 11.1, 11.2, 14.1, 16.1_
  - [ ] 3.2 Create `manifests/vllm-service.yaml`
    - Define Service type NodePort with port 8000 → targetPort 8000
    - Label selector `app: vllm-advanced-server`
    - _Requirements: 5.1, 5.2, 5.3_

- [ ] 4. Checkpoint - Verify base project structure
  - Ensure all files exist: `.gitignore`, `requirements.txt`, `Dockerfile`, `manifests/vllm-deployment.yaml`, `manifests/vllm-service.yaml`
  - Ensure `hyperpod_eks_vllm_basic/` exists with updated README
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 5. Create ALB Ingress and routing manifests
  - [ ] 5.1 Create `manifests/alb-ingress.yaml`
    - Define Ingress with AWS ALB annotations: `kubernetes.io/ingress.class: alb`, `scheme: internal`, `target-type: ip`, `healthcheck-path: /health`, `listen-ports: [{"HTTP": 80}]`
    - Add commented TLS annotations for HTTPS with ACM certificate ARN
    - Add commented sticky session annotation for session affinity
    - Route HTTP/80 to vllm-advanced-server service on port 8000
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.7, 7.2, 7.3_

- [ ] 6. Create Ray Cluster manifest
  - [ ] 6.1 Create `manifests/ray-cluster.yaml`
    - Define KubeRay RayCluster CRD with head node (1 replica, no GPU) and worker group (default 2 replicas, configurable GPUs)
    - Configure `rayStartParams` for distributed vLLM
    - Use same Docker image as vLLM pods
    - Set NCCL environment variables (`NCCL_SOCKET_IFNAME`, `NCCL_DEBUG`)
    - Add `RAY_ADDRESS` environment variable for vLLM connection
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.7_

- [ ] 7. Create Redis and cache proxy
  - [ ] 7.1 Create `manifests/redis.yaml`
    - Define Redis Deployment with PVC (1Gi default) for persistent storage
    - Define Redis Service exposing port 6379
    - Set resource limits (512Mi memory)
    - Add labels: `app: vllm-advanced-server`, `component: redis`
    - _Requirements: 9.1, 9.2_
  - [ ] 7.2 Implement `cache_proxy.py`
    - Create Python script that runs as a sidecar/standalone proxy
    - Accept configurable listen port, vLLM backend URL, Redis URL, and TTL (default 3600s)
    - Compute SHA-256 hash of prompt prefix for cache key
    - Check Redis for cached metadata on incoming requests; on hit, add routing hints
    - On cache miss, forward to vLLM, store metadata in Redis with TTL
    - On Redis failure, bypass cache transparently and log warning
    - Expose `/health` endpoint for readiness probes
    - _Requirements: 9.3, 9.4, 9.7_
  - [ ]* 7.3 Write property test for cache key determinism (Property 1)
    - **Property 1: Cache key determinism and consistency**
    - Generate random prompt strings, verify SHA-256 cache key is deterministic (same input → same output) and different prompts produce different keys with high probability
    - Use Hypothesis library with minimum 100 iterations
    - **Validates: Requirements 9.4**
  - [ ]* 7.4 Write unit tests for cache proxy
    - Test Redis bypass on `ConnectionError` (mock Redis)
    - Test correct metadata JSON structure stored in Redis
    - Test `/health` endpoint returns 200
    - _Requirements: 9.7_

- [ ] 8. Checkpoint - Verify infrastructure manifests and cache proxy
  - Ensure all manifest files exist in `manifests/`: `vllm-deployment.yaml`, `vllm-service.yaml`, `alb-ingress.yaml`, `ray-cluster.yaml`, `redis.yaml`
  - Ensure `cache_proxy.py` exists at project root
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 9. Create monitoring manifests (Prometheus + Grafana)
  - [ ] 9.1 Create `manifests/prometheus.yaml`
    - Define Prometheus Deployment with ConfigMap for `prometheus.yml`
    - Configure Kubernetes service discovery (`kubernetes_sd_configs`) targeting pods with label `app: vllm-advanced-server`
    - Set scrape interval 15s, scrape path `/metrics`
    - Define Service on port 9090
    - _Requirements: 12.1, 12.2, 12.5_
  - [ ] 9.2 Create `manifests/grafana.yaml`
    - Define Grafana Deployment with ConfigMap for datasource provisioning (Prometheus URL) and dashboard JSON
    - Pre-configure dashboard panels: request latency (P50/P95/P99), throughput (req/s, tokens/s), GPU memory utilization, KV cache utilization, batch size distribution, queue depth
    - Define Service on port 3000
    - _Requirements: 12.3, 12.4_

- [ ] 10. Create autoscaling manifests (HPA + Prometheus Adapter)
  - [ ] 10.1 Create `manifests/hpa.yaml`
    - Define HPA targeting vLLM Deployment
    - Scale on custom metric `vllm:num_requests_waiting` (pending queue depth)
    - Min replicas: 1, Max replicas: 4
    - Scale-up stabilization: 60s, Scale-down stabilization: 300s
    - _Requirements: 13.1, 13.2, 13.3_
  - [ ] 10.2 Create `manifests/prometheus-adapter.yaml`
    - Define Prometheus Adapter Deployment with ConfigMap rules
    - Map `vllm:num_requests_waiting` to Kubernetes custom metrics API
    - Register as APIService for `custom.metrics.k8s.io`
    - _Requirements: 13.4_

- [ ] 11. Create disaggregated serving manifest
  - [ ] 11.1 Create `manifests/disaggregated-serving.yaml`
    - Define separate Deployments for prefill and decode worker pools
    - Prefill workers: optimized for prompt processing (higher batch size)
    - Decode workers: optimized for token generation (lower latency)
    - Document as experimental, note minimum vLLM version required (v0.6.0+)
    - _Requirements: 15.1, 15.5_

- [ ] 12. Implement advanced client script
  - [ ] 12.1 Implement `client.py`
    - Accept `--url` flag supporting ALB endpoint URLs (default `http://localhost:8000`)
    - Accept `--lora` flag to specify LoRA adapter name in the `model` field
    - Accept `--json-mode` flag to enable `response_format: {"type": "json_object"}`
    - Accept `--schema` flag to pass a JSON schema file path for `guided_json`
    - Accept `--streaming` flag for SSE streaming responses
    - Query `/v1/models` to detect loaded model name
    - Try chat completion first, fall back to text completion on 4xx
    - Print response to stdout; print errors to stderr with status code
    - _Requirements: 14.3, 17.1, 17.2, 18.1, 18.2, 18.3_
  - [ ]* 12.2 Write property test for client request payload completeness (Property 2)
    - **Property 2: Client request payload completeness**
    - Generate random (adapter_name, json_mode, schema) tuples, verify constructed request payload contains all specified fields: adapter name in `model` field when LoRA specified, `response_format` with `type: json_object` when JSON mode enabled, schema in `guided_json` when schema provided
    - Use Hypothesis library with minimum 100 iterations
    - **Validates: Requirements 14.3, 17.1**
  - [ ]* 12.3 Write unit tests for client script
    - Test request construction with each flag combination (--lora, --json-mode, --schema)
    - Test fallback from chat completion to text completion on 4xx
    - _Requirements: 14.3, 17.1, 17.2_

- [ ] 13. Implement benchmark script
  - [ ] 13.1 Implement `benchmark.py`
    - Accept `--url`, `--concurrency N`, `--num-requests N`, `--prompt`, `--timeout` arguments
    - Use `asyncio` + `aiohttp` for concurrent request generation
    - Measure throughput (tokens/s), time-to-first-token (TTFT), end-to-end latency (P50/P95/P99), inter-token latency (ITL)
    - Support `--compare` mode: run same workload with two configurations, output side-by-side table
    - Support `--output json` for JSON format and human-readable table (default)
    - Compute percentiles correctly: P50 ≤ P95 ≤ P99 ≤ max
    - _Requirements: 18.4, 18.5, 18.6_
  - [ ]* 13.2 Write property test for benchmark percentile computation (Property 3)
    - **Property 3: Benchmark percentile computation correctness**
    - Generate random non-empty float lists, compute percentiles, verify P50 ≤ P95 ≤ P99 ≤ max
    - Use Hypothesis library with minimum 100 iterations
    - **Validates: Requirements 18.4**
  - [ ]* 13.3 Write property test for benchmark results serialization round-trip (Property 4)
    - **Property 4: Benchmark results serialization round-trip**
    - Generate random valid benchmark result dicts, serialize to JSON, deserialize, verify field equality
    - Use Hypothesis library with minimum 100 iterations
    - **Validates: Requirements 18.5**
  - [ ]* 13.4 Write unit tests for benchmark script
    - Test output format (table vs JSON) for sample data
    - Test `--compare` mode produces side-by-side output
    - _Requirements: 18.5, 18.6_

- [ ] 14. Checkpoint - Verify all Python scripts and tests
  - Ensure `client.py`, `benchmark.py`, `cache_proxy.py` exist at project root
  - Ensure all property tests and unit tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 15. Create JSON schema examples and Makefile
  - [ ] 15.1 Create JSON schema files in `schemas/`
    - Create `schemas/entity-extraction.json` — schema for extracting entities from text
    - Create `schemas/classification.json` — schema for text classification output
    - Create `schemas/structured-summary.json` — schema for structured summarization output
    - _Requirements: 17.4_
  - [ ] 15.2 Create the Makefile
    - Define variables: `AWS_ACCOUNT_ID`, `AWS_REGION`, `IMAGE_NAME=hyperpod-eks-vllm-advanced`, `ECR_REPO`
    - Add build targets: `build`, `login`, `tag`, `push`
    - Add core targets: `deploy` (base vLLM + service), `delete`, `list-pods`, `watch-logs`, `get-endpoint`
    - Add per-feature targets: `deploy-alb`/`delete-alb`, `deploy-ray`/`delete-ray`, `deploy-redis`/`delete-redis`, `deploy-monitoring`/`delete-monitoring`, `deploy-hpa`/`delete-hpa`, `deploy-disaggregated`/`delete-disaggregated`
    - Add test targets: `test-inference` (run client.py), `benchmark` (run benchmark.py)
    - Add utility targets: `port-forward`, `port-forward-grafana`, `deploy-all`, `delete-all`, `venv`
    - _Requirements: 1.6, 1.7, 2.3, 5.5, 12.7, 19.5, 19.6_

- [ ] 16. Create README.md documentation
  - [ ] 16.1 Write overview, architecture, and Quick Start sections
    - Architecture overview with component diagram (vLLM pods, Ray cluster, ALB, Redis, Prometheus, Grafana)
    - Quick Start section deploying basic multi-GPU setup before additional optimizations
    - Prerequisites section listing required cluster components and verification steps
    - _Requirements: 20.1, 20.3, 20.4_
  - [ ] 16.2 Write feature sections with configuration and verification
    - Feature matrix table: technique, Makefile target, manifest file, vLLM arguments
    - Feature dependency documentation (autoscaling requires monitoring, pipeline parallelism requires Ray)
    - Per-feature sections: tensor parallelism, pipeline parallelism, ALB ingress, prefix caching, Redis L3 cache, speculative decoding, chunked prefill, LoRA adapters, FP8 quantization, structured output, disaggregated serving, monitoring, autoscaling
    - Each section: prerequisites, configuration steps, verification procedure
    - Model configuration table mapping models to tensor parallelism degree and GPU count
    - _Requirements: 2.5, 2.7, 3.4, 4.6, 5.4, 6.5, 6.6, 7.4, 8.2, 8.3, 8.4, 9.5, 9.6, 10.2, 10.3, 10.4, 11.3, 11.4, 12.6, 13.5, 13.6, 14.2, 14.4, 14.5, 15.2, 15.3, 15.4, 16.2, 16.3, 16.4, 17.3, 18.7, 20.2_
  - [ ] 16.3 Write troubleshooting and learning path sections
    - Troubleshooting section: OOM errors, Ray cluster connectivity, ALB health check failures, Redis connection timeouts, model download failures
    - Recommended learning path guiding reader through techniques in order of increasing complexity
    - Benchmark commands and interpretation guidance for each optimization technique
    - _Requirements: 20.5, 20.6_

- [ ] 17. Final checkpoint - Verify complete project
  - Verify all files exist in `hyperpod_eks_vllm_advanced/`: README.md, Makefile, Dockerfile, requirements.txt, .gitignore, client.py, benchmark.py, cache_proxy.py
  - Verify all manifests exist in `manifests/`: vllm-deployment.yaml, vllm-service.yaml, alb-ingress.yaml, ray-cluster.yaml, redis.yaml, prometheus.yaml, grafana.yaml, hpa.yaml, prometheus-adapter.yaml, disaggregated-serving.yaml
  - Verify all schemas exist in `schemas/`: entity-extraction.json, classification.json, structured-summary.json
  - Verify `hyperpod_eks_vllm_basic/` exists with updated README
  - Verify all requirements are covered by implementation tasks
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document using Hypothesis
- Unit tests validate specific examples and edge cases
- All Kubernetes manifests are independent — each feature can be deployed/removed without affecting the base deployment
- The design specifies Python 3 with Hypothesis for property-based testing; no language selection needed

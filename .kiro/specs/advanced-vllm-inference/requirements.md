# Requirements Document

## Introduction

This document defines the requirements for an advanced vLLM inference showcase project on HyperPod EKS. The project graduates from the basic single-GPU experiment (renamed from `_experiments/hyperpod_eks_vllm` to `hyperpod_eks_vllm_basic`) into a proper top-level project directory (`hyperpod_eks_vllm_advanced`) that demonstrates production-grade inference patterns: multi-GPU/multi-node model parallelism, VPC-native networking with ALB, intelligent request routing, distributed KV cache sharing with an external L3 cache layer, and a suite of vLLM optimization techniques. Both projects share the common `hyperpod_eks_vllm_` prefix to indicate they belong to the same family. The goal is a learning/showcase project that uses production-grade patterns so practitioners can understand and adapt each technique independently. A key design principle is modularity: each advanced technique can be independently enabled or disabled, so users can clearly see which parts of the implementation serve which purpose.

## Glossary

- **vLLM_Server**: The vLLM inference engine running inside one or more containers on the HyperPod EKS cluster, serving an OpenAI-compatible API
- **Inference_Gateway**: The combination of Kubernetes Service, Ingress, and AWS ALB that exposes vLLM_Server endpoints within the VPC
- **ALB**: AWS Application Load Balancer provisioned by the AWS Load Balancer Controller to route HTTP traffic to vLLM_Server pods
- **Tensor_Parallelism**: A vLLM parallelism strategy that shards model layers across multiple GPUs within a single node
- **Pipeline_Parallelism**: A vLLM parallelism strategy that distributes model layers sequentially across multiple nodes, each contributing one or more GPUs
- **Ray_Cluster**: A Ray runtime deployed on Kubernetes that coordinates multi-node vLLM workers for distributed inference
- **KV_Cache**: The key-value attention cache maintained by vLLM during inference to avoid recomputing attention for previously processed tokens
- **L3_Cache**: An external Redis (or compatible) database used as a third-level cache to persist and share KV cache entries across vLLM_Server instances
- **Prefix_Cache**: vLLM's automatic prefix caching feature that reuses KV_Cache entries for requests sharing common prompt prefixes
- **Speculative_Decoding**: A vLLM optimization where a smaller draft model generates candidate tokens that the main model verifies in parallel, reducing latency
- **Disaggregated_Serving**: A vLLM architecture that separates prefill (prompt processing) and decode (token generation) into distinct worker pools
- **Chunked_Prefill**: A vLLM optimization that breaks long prompt prefill into smaller chunks, interleaving them with decode steps to improve time-to-first-token
- **LoRA_Adapter**: A lightweight fine-tuned adapter that can be loaded on top of a base model at runtime without reloading the full model weights
- **HPA**: Kubernetes Horizontal Pod Autoscaler that scales the number of vLLM_Server replicas based on custom metrics
- **Monitoring_Stack**: A Prometheus and Grafana deployment that collects and visualizes inference metrics from vLLM_Server instances
- **Client_Script**: A Python script that sends inference requests to the vLLM_Server through the Inference_Gateway and displays responses
- **Makefile**: A build automation file providing targets for Docker build, ECR push, Kubernetes deploy, and operational tasks
- **HyperPod_EKS_Cluster**: An Amazon SageMaker HyperPod cluster running in EKS mode with GPU-capable worker nodes
- **FP8_Quantization**: A quantization technique that reduces model weights to 8-bit floating point, enabling larger models to fit on fewer GPUs

## Requirements

### Requirement 1: Project Structure, Naming, and Layout

**User Story:** As a developer, I want the advanced project and the basic experiment to share a common naming prefix and be organized as sibling top-level directories, so that I can easily identify them as related projects.

#### Acceptance Criteria

1. THE advanced project SHALL reside at the top-level directory `hyperpod_eks_vllm_advanced` in the repository root
2. THE existing basic experiment SHALL be moved from `_experiments/hyperpod_eks_vllm` to the top-level directory `hyperpod_eks_vllm_basic`, so that both projects share the `hyperpod_eks_vllm_` prefix
3. THE advanced project SHALL contain README.md, Makefile, Dockerfile, requirements.txt, and .gitignore at the project root level
4. THE advanced project SHALL organize Kubernetes manifests in a `manifests/` subdirectory with separate YAML files for each component (vLLM deployment, service, ingress, Redis, monitoring, autoscaling)
5. THE advanced project SHALL organize Python scripts at the project root level following the repository convention of `snake_case.py` naming
6. THE Makefile SHALL provide targets for `build`, `login`, `tag`, `push`, `deploy`, `delete`, `list-pods`, and `watch-logs` consistent with the repository standard
7. THE Makefile SHALL provide additional targets for deploying individual components (e.g., `deploy-redis`, `deploy-monitoring`, `deploy-alb`) to allow incremental setup
8. THE .gitignore SHALL exclude Python bytecode files, virtual environment directories, `.env` files, and OS-specific metadata files
9. THE `hyperpod_eks_vllm_basic` README.md SHALL be updated to reference `hyperpod_eks_vllm_advanced` as the next step for learning advanced techniques

### Requirement 2: Modular Feature Toggles

**User Story:** As a developer, I want each advanced technique to be independently toggleable, so that I can enable or disable individual features to understand which parts of the implementation serve which purpose.

#### Acceptance Criteria

1. EACH advanced technique (tensor parallelism, pipeline parallelism, ALB ingress, prefix caching, Redis L3 cache, speculative decoding, chunked prefill, monitoring, autoscaling, LoRA adapters, disaggregated serving, FP8 quantization, structured output) SHALL be deployable and removable independently without affecting the base vLLM_Server deployment
2. THE Kubernetes manifests SHALL be organized as separate YAML files per feature in the `manifests/` subdirectory, so that each feature can be applied or removed with a single `kubectl apply -f` or `kubectl delete -f` command
3. THE Makefile SHALL provide per-feature deploy and delete targets (e.g., `deploy-redis` / `delete-redis`, `deploy-monitoring` / `delete-monitoring`, `deploy-alb` / `delete-alb`, `deploy-ray` / `delete-ray`) so that users can toggle features from the command line
4. THE vLLM_Server container arguments that enable optional features (e.g., `--enable-prefix-caching`, `--enable-chunked-prefill`, `--speculative-model`, `--enable-lora`, `--quantization fp8`) SHALL be organized as clearly commented blocks in the deployment manifest, so that users can uncomment or comment individual features
5. THE README.md SHALL include a feature matrix table listing each technique, its Makefile target, its manifest file, and its vLLM arguments, so that users have a single reference for toggling features
6. WHEN a feature is disabled or its manifest is removed, THE base vLLM_Server SHALL continue to function correctly with default settings
7. THE README.md SHALL document the dependencies between features (e.g., autoscaling requires monitoring, pipeline parallelism requires Ray) so that users know which features must be enabled together

### Requirement 3: Multi-GPU Tensor Parallelism

**User Story:** As a developer, I want to serve large models across multiple GPUs on a single node using tensor parallelism, so that I can run models that exceed single-GPU memory.

#### Acceptance Criteria

1. THE vLLM_Server deployment manifest SHALL support configuring `--tensor-parallel-size` to a value matching the number of GPUs requested per pod
2. THE vLLM_Server deployment manifest SHALL request a configurable number of `nvidia.com/gpu` resources (e.g., 2, 4, or 8) matching the tensor parallelism degree
3. WHEN `--tensor-parallel-size` is set to N, THE vLLM_Server SHALL shard the model across N GPUs within the same pod
4. THE README.md SHALL include a configuration table mapping recommended models to their required tensor parallelism degree and GPU count (e.g., Llama-2-70B requires 4 GPUs with tensor-parallel-size=4)
5. THE deployment manifest SHALL mount a shared memory volume (`/dev/shm`) using an emptyDir with medium Memory sized appropriately for multi-GPU inter-process communication

### Requirement 4: Multi-Node Pipeline Parallelism with Ray

**User Story:** As a developer, I want to distribute model inference across multiple nodes using pipeline parallelism, so that I can serve models too large for a single node's GPU memory.

#### Acceptance Criteria

1. THE project SHALL include a Ray_Cluster manifest that deploys a Ray head node and configurable number of Ray worker nodes on the HyperPod_EKS_Cluster
2. THE vLLM_Server SHALL use Ray as the distributed backend to coordinate pipeline parallelism across multiple nodes
3. THE vLLM_Server deployment manifest SHALL support configuring `--pipeline-parallel-size` to distribute model layers across multiple nodes
4. WHEN `--pipeline-parallel-size` is set to M and `--tensor-parallel-size` is set to N, THE vLLM_Server SHALL use M × N total GPUs across M nodes
5. THE Ray_Cluster manifest SHALL configure Ray worker nodes with GPU resource requests matching the tensor parallelism degree per node
6. THE README.md SHALL include step-by-step instructions for deploying a multi-node inference setup with an example configuration (e.g., Llama-2-70B across 2 nodes with 4 GPUs each)
7. IF a Ray worker node becomes unavailable, THEN THE Ray_Cluster SHALL log the disconnection event and the vLLM_Server SHALL report the failure through its health endpoint

### Requirement 5: VPC-Native Service Exposure

**User Story:** As a developer, I want to expose the vLLM inference endpoint within the VPC using a proper Kubernetes Service, so that other applications in the VPC can access it without port-forwarding.

#### Acceptance Criteria

1. THE project SHALL include a Kubernetes Service manifest of type NodePort or LoadBalancer that exposes the vLLM_Server API port within the VPC
2. THE Service manifest SHALL route traffic to vLLM_Server pods using label selectors matching the deployment labels
3. THE Service manifest SHALL expose port 8000 for the OpenAI-compatible API
4. THE README.md SHALL include instructions for discovering the service endpoint (ClusterIP, NodePort, or LoadBalancer DNS) and testing connectivity from within the VPC
5. THE Makefile SHALL provide a `get-endpoint` target that prints the accessible endpoint URL for the vLLM_Server

### Requirement 6: Application Load Balancer Ingress

**User Story:** As a developer, I want to set up an ALB in front of the vLLM inference endpoint, so that I have a stable DNS endpoint with health checking and TLS termination capability.

#### Acceptance Criteria

1. THE project SHALL include a Kubernetes Ingress manifest annotated for the AWS Load Balancer Controller to provision an ALB
2. THE Ingress manifest SHALL configure the ALB as internal (VPC-only) by default using the `alb.ingress.kubernetes.io/scheme: internal` annotation
3. THE Ingress manifest SHALL configure health check annotations pointing to the vLLM_Server `/health` endpoint
4. THE Ingress manifest SHALL route HTTP traffic on port 80 to the vLLM_Server Service on port 8000
5. THE README.md SHALL document the prerequisite of having the AWS Load Balancer Controller installed on the HyperPod_EKS_Cluster
6. THE README.md SHALL include instructions for retrieving the ALB DNS name after deployment and testing the endpoint
7. WHERE TLS termination is desired, THE Ingress manifest SHALL include commented-out annotations for configuring an ACM certificate ARN with HTTPS listener on port 443

### Requirement 7: Intelligent Request Routing and Load Balancing

**User Story:** As a developer, I want intelligent request routing across multiple vLLM replicas, so that inference load is distributed efficiently and requests are routed to the optimal instance.

#### Acceptance Criteria

1. THE vLLM_Server deployment manifest SHALL support configuring multiple replicas for horizontal scaling
2. THE ALB Ingress SHALL distribute requests across all healthy vLLM_Server replicas using round-robin or least-connections routing
3. THE project SHALL include a routing configuration that enables session affinity (sticky sessions) as an optional annotation, so that multi-turn conversations route to the same instance for KV_Cache reuse
4. THE README.md SHALL explain the trade-offs between round-robin routing (even distribution) and session affinity (cache reuse) for inference workloads
5. THE Service manifest SHALL configure readiness probes using the vLLM_Server `/health` endpoint so that the load balancer only routes to instances that have completed model loading

### Requirement 8: Distributed KV Cache Sharing

**User Story:** As a developer, I want vLLM instances to share KV cache entries, so that common prompt prefixes computed by one instance can be reused by others, reducing redundant computation.

#### Acceptance Criteria

1. THE vLLM_Server SHALL be configured with automatic prefix caching enabled (`--enable-prefix-caching`) to reuse KV_Cache entries for requests sharing common prompt prefixes
2. THE project SHALL include documentation explaining how vLLM's built-in prefix caching works at the per-instance level and its benefits for repeated prompt patterns
3. THE README.md SHALL include a demonstration script or instructions that show the latency improvement when sending requests with shared prefixes to the same vLLM_Server instance
4. THE README.md SHALL document the current limitations of cross-instance KV_Cache sharing in vLLM and describe the architectural pattern for achieving it through session affinity and prefix-aware routing

### Requirement 9: Redis L3 Cache for KV Cache

**User Story:** As a developer, I want to use Redis as an external L3 cache layer for KV cache data, so that cache entries persist across pod restarts and can be shared between vLLM instances.

#### Acceptance Criteria

1. THE project SHALL include a Kubernetes manifest that deploys a Redis instance (single-node or Redis Cluster) on the HyperPod_EKS_Cluster
2. THE Redis manifest SHALL configure persistent storage using a PersistentVolumeClaim so that cached data survives pod restarts
3. THE project SHALL include a cache proxy script or sidecar configuration that intercepts vLLM inference requests, computes a cache key from the prompt prefix, and checks Redis for cached KV data before forwarding to the vLLM_Server
4. THE cache proxy SHALL store computed KV-related metadata (prompt hashes, token counts, routing hints) in Redis with a configurable TTL
5. THE README.md SHALL document the L3 cache architecture, explaining how the cache proxy interacts with Redis and the vLLM_Server
6. THE README.md SHALL include performance benchmarking instructions comparing inference latency with and without the Redis L3 cache layer
7. IF Redis is unavailable, THEN THE cache proxy SHALL bypass the cache and forward requests directly to the vLLM_Server without failing

### Requirement 10: Speculative Decoding

**User Story:** As a developer, I want to enable speculative decoding in vLLM, so that I can reduce inference latency by using a smaller draft model to generate candidate tokens verified by the main model.

#### Acceptance Criteria

1. THE vLLM_Server deployment manifest SHALL support configuring speculative decoding via `--speculative-model` and `--num-speculative-tokens` arguments
2. THE README.md SHALL include a configuration example showing how to pair a large target model with a smaller draft model (e.g., Llama-2-70B with Llama-2-7B as draft)
3. THE README.md SHALL explain the speculative decoding trade-offs: reduced latency per token vs. increased GPU memory usage for the draft model
4. THE README.md SHALL include benchmarking instructions comparing tokens-per-second with and without speculative decoding enabled

### Requirement 11: Continuous Batching and Chunked Prefill

**User Story:** As a developer, I want to demonstrate vLLM's continuous batching and chunked prefill optimizations, so that I can maximize throughput and minimize time-to-first-token for concurrent requests.

#### Acceptance Criteria

1. THE vLLM_Server SHALL use continuous batching by default (vLLM's native scheduling behavior) to dynamically batch incoming requests without waiting for a full batch
2. THE vLLM_Server deployment manifest SHALL support configuring `--enable-chunked-prefill` to break long prompt prefill into smaller chunks interleaved with decode steps
3. THE README.md SHALL explain how continuous batching differs from static batching and its impact on throughput under concurrent load
4. THE README.md SHALL explain how chunked prefill improves time-to-first-token for long prompts by allowing decode steps to proceed during prefill
5. THE project SHALL include a benchmarking script that sends concurrent requests and measures throughput (tokens/second) and time-to-first-token with and without chunked prefill enabled


### Requirement 12: Prometheus and Grafana Monitoring

**User Story:** As a developer, I want to monitor inference metrics (latency, throughput, GPU utilization) using Prometheus and Grafana, so that I can observe system behavior and identify bottlenecks.

#### Acceptance Criteria

1. THE vLLM_Server deployment manifest SHALL expose the Prometheus metrics endpoint that vLLM provides natively
2. THE project SHALL include a Kubernetes manifest that deploys a Prometheus instance configured to scrape metrics from all vLLM_Server pods
3. THE project SHALL include a Kubernetes manifest that deploys a Grafana instance with a pre-configured dashboard for vLLM inference metrics
4. THE Grafana dashboard SHALL display panels for: request latency (P50, P95, P99), throughput (requests/second, tokens/second), GPU memory utilization, KV cache utilization, batch size distribution, and queue depth
5. THE Prometheus configuration SHALL use Kubernetes service discovery to automatically detect new vLLM_Server pods as they scale
6. THE README.md SHALL include instructions for accessing the Grafana dashboard via port-forward and interpreting the key metrics
7. THE Makefile SHALL provide a `deploy-monitoring` target that deploys both Prometheus and Grafana with a single command

### Requirement 13: Autoscaling with Custom Metrics

**User Story:** As a developer, I want vLLM replicas to autoscale based on inference load metrics, so that the system scales up during high demand and scales down during idle periods.

#### Acceptance Criteria

1. THE project SHALL include an HPA manifest that scales vLLM_Server replicas based on custom metrics from Prometheus
2. THE HPA manifest SHALL configure scaling based on at least one of: pending request queue depth, GPU utilization, or request latency
3. THE HPA manifest SHALL define configurable minimum and maximum replica counts with sensible defaults (min: 1, max: 4)
4. THE project SHALL include a Prometheus Adapter or KEDA configuration that exposes vLLM Prometheus metrics as Kubernetes custom metrics for the HPA
5. THE README.md SHALL document the autoscaling architecture, including how metrics flow from vLLM to Prometheus to the HPA
6. THE README.md SHALL include a load testing procedure that demonstrates autoscaling behavior by generating sustained inference traffic

### Requirement 14: LoRA Adapter Hot-Swapping

**User Story:** As a developer, I want to load and swap LoRA adapters at runtime on a base model, so that I can serve multiple fine-tuned model variants from a single vLLM instance for multi-tenant use cases.

#### Acceptance Criteria

1. THE vLLM_Server deployment manifest SHALL support configuring `--enable-lora` to enable LoRA adapter serving
2. THE vLLM_Server deployment manifest SHALL support configuring `--lora-modules` to specify one or more LoRA adapter paths or Hugging Face identifiers
3. THE Client_Script SHALL demonstrate sending requests that specify different LoRA adapter names in the `model` field of the OpenAI-compatible API request
4. THE README.md SHALL explain the LoRA serving architecture: how a single base model serves multiple adapters, memory overhead per adapter, and maximum concurrent adapters
5. THE README.md SHALL include an example workflow for adding a new LoRA adapter to a running vLLM_Server without restarting the pod

### Requirement 15: Disaggregated Prefill and Decode

**User Story:** As a developer, I want to separate prefill and decode phases into distinct worker pools, so that long prompt processing does not block token generation for other requests.

#### Acceptance Criteria

1. THE project SHALL include deployment manifests that configure separate vLLM worker pools for prefill and decode phases using vLLM's disaggregated serving configuration
2. THE README.md SHALL explain the disaggregated serving architecture: how prefill workers process prompts and hand off to decode workers for token generation
3. THE README.md SHALL document the benefits of disaggregated serving for workloads with mixed short and long prompts
4. THE README.md SHALL include configuration examples showing how to allocate GPU resources between prefill and decode worker pools
5. IF disaggregated serving is not yet stable in the deployed vLLM version, THEN THE README.md SHALL document the feature as experimental and provide the minimum vLLM version required

### Requirement 16: FP8 Quantization

**User Story:** As a developer, I want to serve models using FP8 quantization, so that I can fit larger models on fewer GPUs with minimal quality degradation.

#### Acceptance Criteria

1. THE vLLM_Server deployment manifest SHALL support configuring `--quantization fp8` to enable FP8 quantization at model load time
2. THE README.md SHALL include a comparison table showing GPU memory usage for the same model with and without FP8 quantization (e.g., Llama-2-70B in FP16 vs. FP8)
3. THE README.md SHALL explain the trade-offs of FP8 quantization: reduced memory footprint and potential throughput improvement vs. minor quality degradation
4. THE README.md SHALL document which GPU architectures support FP8 (e.g., NVIDIA H100, L40S) and how to verify hardware compatibility on HyperPod_EKS_Cluster nodes

### Requirement 17: Structured Output and JSON Mode

**User Story:** As a developer, I want to use vLLM's structured output capabilities, so that I can guarantee model responses conform to a specified JSON schema or format.

#### Acceptance Criteria

1. THE Client_Script SHALL demonstrate sending requests with `response_format: {"type": "json_object"}` to enable JSON mode in the vLLM_Server
2. THE Client_Script SHALL demonstrate sending requests with a JSON schema in the `guided_json` parameter to constrain output to a specific structure
3. THE README.md SHALL explain how vLLM implements structured output using guided decoding and its impact on inference latency
4. THE project SHALL include example JSON schemas for common use cases (e.g., entity extraction, classification, structured summarization) in a `schemas/` subdirectory

### Requirement 18: Advanced Client and Benchmarking Tools

**User Story:** As a developer, I want a comprehensive client toolkit that supports all advanced features and can benchmark inference performance, so that I can test and measure each optimization technique.

#### Acceptance Criteria

1. THE Client_Script SHALL support sending requests through the ALB endpoint URL in addition to localhost port-forward
2. THE Client_Script SHALL support specifying LoRA adapter names via a command-line argument
3. THE Client_Script SHALL support enabling JSON mode and passing a JSON schema file via command-line arguments
4. THE project SHALL include a benchmarking script (`benchmark.py`) that measures throughput (tokens/second), time-to-first-token, end-to-end latency, and inter-token latency under configurable concurrency levels
5. THE benchmarking script SHALL output results in both human-readable table format and JSON format for programmatic consumption
6. THE benchmarking script SHALL support a `--compare` mode that runs the same workload with different configurations (e.g., with/without prefix caching, with/without speculative decoding) and displays a side-by-side comparison
7. THE README.md SHALL include example benchmark commands and interpretation guidance for each optimization technique

### Requirement 19: Docker Image for Advanced Features

**User Story:** As a developer, I want a Docker image that includes all dependencies for advanced vLLM features, so that all optimization techniques work out of the box.

#### Acceptance Criteria

1. THE Dockerfile SHALL use an NVIDIA CUDA base image compatible with FP8 quantization and multi-GPU communication (CUDA 12.4+ with NCCL)
2. THE Dockerfile SHALL install vLLM with Ray support for multi-node distributed inference
3. THE Dockerfile SHALL install the Redis client library (redis-py) for L3 cache integration
4. THE Dockerfile SHALL pin specific versions of vLLM and key dependencies in a requirements file for reproducibility
5. WHEN the `make build` command is executed, THE Makefile SHALL build the Docker image with the tag `hyperpod-eks-vllm-advanced`
6. WHEN the `make push` command is executed, THE Makefile SHALL push the image to `842413447717.dkr.ecr.{region}.amazonaws.com/hyperpod-eks-vllm-advanced:latest`

### Requirement 20: Documentation and Learning Guide

**User Story:** As a developer, I want comprehensive documentation that explains each advanced technique with architecture diagrams and step-by-step instructions, so that I can learn and reproduce each pattern independently.

#### Acceptance Criteria

1. THE README.md SHALL include an architecture overview section with a diagram showing all components (vLLM pods, Ray cluster, ALB, Redis, Prometheus, Grafana) and their interactions
2. THE README.md SHALL organize advanced techniques into clearly labeled sections, each with its own prerequisites, configuration steps, and verification procedure
3. THE README.md SHALL include a "Quick Start" section that deploys a basic multi-GPU setup before introducing additional optimizations
4. THE README.md SHALL include a prerequisites section listing required cluster components (AWS Load Balancer Controller, GPU nodes, Prometheus Adapter) and how to verify their availability
5. THE README.md SHALL include a troubleshooting section covering common failure modes (OOM errors, Ray cluster connectivity, ALB health check failures, Redis connection timeouts)
6. THE README.md SHALL include a recommended learning path that guides the reader through techniques in order of increasing complexity

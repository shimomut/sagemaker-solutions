# Requirements Document

## Introduction

This document defines the requirements for a learning-focused experimental project that demonstrates how to run inference workloads on a HyperPod EKS cluster using vLLM. The project lives under `_experiments/hyperpod_eks_vllm` and follows the repository's standard project layout (README.md, Makefile, Dockerfile, Kubernetes manifests, Python scripts). The goal is to keep the implementation as simple as possible while covering key vLLM features such as the OpenAI-compatible API server, model serving with GPU resources, and basic client interaction.

## Glossary

- **vLLM_Server**: The vLLM inference engine running inside a container on the HyperPod EKS cluster, serving an OpenAI-compatible API
- **Client_Script**: A Python script that sends inference requests to the vLLM_Server and displays responses
- **Deployment_Manifest**: A Kubernetes YAML file that defines the vLLM_Server pod, service, and resource requirements
- **Makefile**: A build automation file providing targets for Docker build, ECR push, Kubernetes deploy, and log viewing
- **Dockerfile**: A container definition that packages the vLLM runtime and dependencies into a Docker image
- **HyperPod_EKS_Cluster**: An Amazon SageMaker HyperPod cluster running in EKS mode with GPU-capable worker nodes
- **Hugging_Face_Hub**: The Hugging Face model repository (huggingface.co) from which vLLM downloads pre-trained models by specifying an organization/model identifier (e.g., `facebook/opt-1.3b`)
- **Model_Identifier**: A string in the format `{organization}/{model_name}` that uniquely identifies a model on the Hugging_Face_Hub

## Requirements

### Requirement 1: Project Structure

**User Story:** As a developer, I want the project to follow the repository's standard layout, so that I can navigate and use it consistently with other projects.

#### Acceptance Criteria

1. THE project SHALL contain a README.md, Makefile, Dockerfile, deployment.yaml, client.py, requirements.txt, and .gitignore at the `_experiments/hyperpod_eks_vllm` directory level
2. THE Makefile SHALL provide targets for `build`, `login`, `tag`, `push`, `deploy`, `delete`, `list-pods`, and `watch-logs` consistent with the repository's standard Kubernetes operations
3. THE .gitignore SHALL exclude Python bytecode files, virtual environment directories, and OS-specific metadata files

### Requirement 2: Docker Image Build

**User Story:** As a developer, I want to build a Docker image containing the vLLM runtime, so that I can deploy it as a container on the HyperPod EKS cluster.

#### Acceptance Criteria

1. THE Dockerfile SHALL use an NVIDIA CUDA base image that includes the Python runtime
2. THE Dockerfile SHALL install vLLM and its dependencies via pip
3. WHEN the `make build` command is executed, THE Makefile SHALL build the Docker image with a tag matching the project name
4. WHEN the `make login` command is executed, THE Makefile SHALL authenticate to the ECR registry using `aws ecr get-login-password`
5. WHEN the `make push` command is executed, THE Makefile SHALL push the tagged image to the ECR repository following the pattern `{account}.dkr.ecr.{region}.amazonaws.com/hyperpod-eks-vllm:latest`

### Requirement 3: Kubernetes Deployment

**User Story:** As a developer, I want to deploy the vLLM server onto the HyperPod EKS cluster using a Kubernetes manifest, so that the model is served on GPU nodes.

#### Acceptance Criteria

1. THE Deployment_Manifest SHALL define a Kubernetes Deployment with the label `app: vllm-server`
2. THE Deployment_Manifest SHALL request at least 1 `nvidia.com/gpu` resource for the vLLM_Server container
3. THE Deployment_Manifest SHALL include a toleration for the `nvidia.com/gpu` taint so that the pod schedules on GPU nodes
4. THE Deployment_Manifest SHALL mount a shared memory volume (`/dev/shm`) using an emptyDir with medium Memory to support vLLM tensor operations
5. THE Deployment_Manifest SHALL define a Kubernetes Service of type ClusterIP that routes traffic to the vLLM_Server pod on the API port
6. THE Deployment_Manifest SHALL configure the vLLM_Server container to launch the OpenAI-compatible API server with a configurable model name via environment variable or command arguments
7. WHEN the `make deploy` command is executed, THE Makefile SHALL apply the Deployment_Manifest to the cluster using `kubectl apply`

### Requirement 4: Client Interaction

**User Story:** As a developer, I want a simple Python client script that sends requests to the vLLM server, so that I can test and learn how to interact with the OpenAI-compatible API.

#### Acceptance Criteria

1. THE Client_Script SHALL send chat completion requests to the vLLM_Server using the OpenAI-compatible `/v1/chat/completions` endpoint
2. THE Client_Script SHALL accept the server URL as a command-line argument or use a default localhost URL with port-forwarding
3. THE Client_Script SHALL print the model response text to standard output
4. IF the vLLM_Server returns an HTTP error status, THEN THE Client_Script SHALL print the error status code and response body to standard error
5. THE Client_Script SHALL use only the `requests` library for HTTP communication to keep dependencies minimal

### Requirement 5: Documentation

**User Story:** As a developer, I want clear documentation explaining how to build, deploy, and test the vLLM inference server, so that I can follow the steps to learn vLLM on HyperPod EKS.

#### Acceptance Criteria

1. THE README.md SHALL include an overview section describing the project purpose and the vLLM features demonstrated
2. THE README.md SHALL include a prerequisites section listing required tools (kubectl, Docker, AWS CLI) and cluster requirements (GPU nodes on HyperPod EKS)
3. THE README.md SHALL include step-by-step instructions for building the Docker image, pushing to ECR, and deploying to the cluster
4. THE README.md SHALL include instructions for using `kubectl port-forward` to access the vLLM_Server from a local machine
5. THE README.md SHALL include an example of running the Client_Script to send a chat completion request and view the response
6. THE README.md SHALL include a section describing key vLLM configuration options (model selection, tensor parallelism, GPU memory utilization) with brief explanations

### Requirement 6: vLLM Configuration

**User Story:** As a developer, I want the deployment to expose key vLLM configuration options, so that I can experiment with different settings while learning.

#### Acceptance Criteria

1. THE Deployment_Manifest SHALL allow configuring the served model name through an environment variable or container command arguments
2. THE Deployment_Manifest SHALL allow configuring the tensor parallelism degree through an environment variable or container command arguments for multi-GPU setups
3. THE Deployment_Manifest SHALL allow configuring the GPU memory utilization ratio through an environment variable or container command arguments
4. THE Deployment_Manifest SHALL set sensible default values for model name, tensor parallelism (1), and GPU memory utilization (0.9)

### Requirement 7: Hugging Face Model Support and Switching

**User Story:** As a developer, I want to serve models from Hugging Face Hub and switch between them, so that I can experiment with different models on the same cluster without rebuilding the Docker image.

#### Acceptance Criteria

1. THE Deployment_Manifest SHALL reference models using a Hugging_Face_Hub Model_Identifier (e.g., `facebook/opt-1.3b`) in the vLLM_Server startup configuration
2. THE Deployment_Manifest SHALL use `facebook/opt-1.3b` as the default Model_Identifier so that the project works on a single GPU without requiring large amounts of GPU memory
3. THE README.md SHALL list at least three recommended Hugging_Face_Hub models of varying sizes suitable for experimentation (e.g., `facebook/opt-1.3b`, `mistralai/Mistral-7B-Instruct-v0.3`, `meta-llama/Llama-3.1-8B-Instruct`) along with their approximate GPU memory requirements
4. WHEN a developer changes the Model_Identifier environment variable in the Deployment_Manifest and runs `make deploy`, THE vLLM_Server SHALL download and serve the newly specified model from the Hugging_Face_Hub
5. THE README.md SHALL include step-by-step instructions for switching between models by editing the Model_Identifier in the Deployment_Manifest and redeploying
6. WHERE a Hugging_Face_Hub model requires authentication, THE Deployment_Manifest SHALL support passing a Hugging Face access token through a Kubernetes Secret or environment variable
7. IF the vLLM_Server fails to download or load the specified Model_Identifier, THEN THE vLLM_Server SHALL log a descriptive error message including the Model_Identifier that failed to load
8. THE Client_Script SHALL query the vLLM_Server `/v1/models` endpoint to display the currently loaded model name before sending chat completion requests

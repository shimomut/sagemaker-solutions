# Repository Guide for Claude

This repository contains AWS SageMaker solutions and utilities. It follows the conventions below. This file is self-contained — read it before making changes.

---

## Technical knowledge base (read this when working on HyperPod behavior)

The curated HyperPod mental model lives in [docs/](docs/):

- [docs/hyperpod-mental-model.md](docs/hyperpod-mental-model.md) — the main curated doc. Read it before answering questions about how HyperPod behaves; don't rely on training-data assumptions ("basically EC2 + Slurm/EKS" is the trap).
- [docs/mental-model/](docs/mental-model/) — dedicated supplemental docs for large topics, linked from the main doc.
- [docs/knowledge-updates/](docs/knowledge-updates/) — staging inbox for new findings, plus the maintenance process.

**When you learn something new about HyperPod during a session**, do NOT edit the main doc mid-discovery. Append a classified finding to a dated file `docs/knowledge-updates/hyperpod-new-knowledge-<YYYY-MM-DD>.md` (copy `docs/knowledge-updates/TEMPLATE.md` if today's file doesn't exist). **When asked to curate / "brush up the docs"**, run the merge → archive → log process defined in [docs/README.md](docs/README.md).

---

## Product Overview

This repository contains AWS SageMaker solutions and utilities across the full spectrum of AI/ML capabilities. It provides practical implementations, automation scripts, and best practices for various SageMaker services.

### Key Components

#### HyperPod Solutions
- **Cluster Management**: Scripts for creating, scaling, and deleting HyperPod clusters with retry logic and incremental scaling
- **EKS Integration**: Kubernetes deployments, webhooks, and utilities for HyperPod EKS clusters
- **Slurm Integration**: Job scheduling, auto-resume functionality, and multi-user management for HyperPod Slurm clusters

#### Training Solutions
- **Training Jobs**: Utilities for SageMaker Training Jobs, including distributed training patterns
- **Model Training**: Custom training scripts, hyperparameter optimization, and experiment management

#### Inference Solutions
- **Real-time Inference**: Endpoint deployment, auto-scaling, and monitoring utilities
- **Batch Inference**: Batch transform jobs and large-scale inference patterns
- **Multi-model Endpoints**: Solutions for hosting multiple models efficiently

#### Shared Infrastructure
- **Storage Solutions**: FSx, EFS, and S3 integration patterns for distributed storage
- **Monitoring & Observability**: Health checks, profiling tools, and event handling
- **Infrastructure Utilities**: Network manipulation, SSSD configuration, and various operational tools

### Target Users
- ML Engineers working with SageMaker training and inference
- Data Scientists implementing ML workflows
- DevOps Engineers managing SageMaker infrastructure
- Solutions Architects implementing SageMaker deployments

---

## Project Structure

### Directory Organization

Each top-level directory represents a specific SageMaker solution or utility:

- **`hyperpod_*`**: HyperPod-specific solutions and utilities
  - `hyperpod_eks_*`: EKS-specific implementations
  - `hyperpod_slurm_*`: Slurm-specific implementations
  - `hyperpod_*`: General cluster management tools
- **`training_*`**: SageMaker Training Job solutions
  - `training_distributed_*`: Distributed training patterns
  - `training_custom_*`: Custom training implementations
  - `training_*`: General training utilities
- **`inference_*`**: SageMaker Inference solutions
  - `inference_realtime_*`: Real-time endpoint solutions
  - `inference_batch_*`: Batch transform solutions
  - `inference_*`: General inference utilities
- **`sagemaker_*`**: Cross-service SageMaker utilities
  - `sagemaker_pipelines_*`: ML workflow solutions
  - `sagemaker_processing_*`: Data processing solutions
  - `sagemaker_*`: General SageMaker utilities

#### Archived & Experimental
- **`_archived/`**: Deprecated or superseded implementations
- **`_experiments/`**: Proof-of-concept and experimental code

### Standard Project Layout

Each solution directory typically contains:

```
sagemaker_solution_name/
├── README.md              # Usage instructions and overview
├── Makefile               # Common operations (build, deploy, etc.)
├── main_script.py         # Primary implementation
├── requirements.txt       # Python dependencies
├── Dockerfile             # Container definition (for containerized solutions)
├── deployment.yaml        # Kubernetes manifests (for HyperPod EKS solutions)
├── job.sh                 # Slurm job script (for HyperPod Slurm solutions)
├── train.py               # Training script (for Training Job solutions)
├── inference.py           # Inference script (for Endpoint solutions)
├── .gitignore             # Local ignores
└── test-data/             # Sample data or configurations
```

### Naming Conventions

#### Directories
- Use underscores for separation: `hyperpod_eks_auto_node_taints`, `training_distributed_pytorch`
- Prefix with service type: `hyperpod_*`, `training_*`, `inference_*`, `sagemaker_*`
- Use descriptive names indicating functionality

#### Files
- Python scripts: `snake_case.py`
- Kubernetes manifests: `kebab-case.yaml`
- Shell scripts: `kebab-case.sh`
- Documentation: `UPPERCASE.md` for main docs, `lowercase.md` for others
- Training scripts: `train.py`, `inference.py` for standard entry points

#### Docker Images
- Repository: `{service-name}` (matches directory name without service prefix)
- Tag: `latest` for current version
- Full path: `842413447717.dkr.ecr.{region}.amazonaws.com/{service-name}:latest`

### Configuration Patterns

#### HyperPod Solutions
- Use `provisioning_parameters.json` for HyperPod cluster configuration
- Store certificates in `certs/` subdirectory
- Use `lcc/` subdirectory for lifecycle scripts

#### Training Solutions
- Use `hyperparameters.json` for training job parameters
- Store training data references in `data/` subdirectory
- Model artifacts output to S3 paths defined in configuration

#### Inference Solutions
- Use `model.tar.gz` for model artifacts
- Store endpoint configuration in `endpoint_config.json`
- Use `code/` subdirectory for custom inference code

#### General Patterns
- Place test data in `test-data/` subdirectory
- Store utilities in `utils/` subdirectory
- Use `requirements.txt` for Python dependencies
- Store IAM policies in `policies/` subdirectory

---

## Technology Stack

### Core Technologies
- **Python 3**: Primary language for scripts and utilities
- **Docker**: Containerization for deployments
- **Kubernetes**: Container orchestration via EKS
- **AWS SDK (boto3)**: AWS service integration
- **Slurm**: Job scheduling and workload management (HyperPod)

### SageMaker Services
- **AWS SageMaker HyperPod**: Managed distributed ML training infrastructure
- **SageMaker Training Jobs**: Managed training service with built-in algorithms
- **SageMaker Endpoints**: Real-time inference hosting
- **SageMaker Batch Transform**: Large-scale batch inference
- **SageMaker Processing**: Data processing and feature engineering
- **SageMaker Pipelines**: ML workflow orchestration

### Infrastructure
- **Amazon EKS**: Kubernetes service for container workloads
- **Amazon ECR**: Container registry (842413447717.dkr.ecr.{region}.amazonaws.com)
- **FSx Lustre**: High-performance file system
- **EFS**: Elastic file system for shared storage
- **S3**: Object storage for data and model artifacts

### Common Commands

#### Docker Operations
```bash
make build        # Build Docker image
make login        # Login to ECR (or login-ecr)
make tag          # Tag image for ECR
make push         # Push to ECR registry
```

#### Kubernetes Operations (HyperPod EKS)
```bash
make deploy       # Deploy to Kubernetes
make delete       # Remove deployment
make list-pods    # List running pods
make watch-logs   # Follow logs (or watch-logs-all)
```

#### Slurm Operations (HyperPod Slurm)
```bash
make enqueue      # Submit job to Slurm queue
make alloc        # Allocate resources
make run          # Run with srun
make q            # Check queue status
make log          # Tail output logs
```

#### SageMaker Operations
```bash
# Training Jobs
python train.py --job-name my-training-job
aws sagemaker describe-training-job --training-job-name my-job

# Endpoints
python deploy.py --endpoint-name my-endpoint
aws sagemaker describe-endpoint --endpoint-name my-endpoint

# Batch Transform
python batch_transform.py --job-name my-transform-job
aws sagemaker describe-transform-job --transform-job-name my-job
```

### Development Patterns
- Use Makefiles for common operations (especially HyperPod solutions)
- ECR repositories follow pattern: `{account}.dkr.ecr.{region}.amazonaws.com/{service}:latest`
- Python scripts use argparse for CLI interfaces
- Kubernetes deployments use consistent labeling (`app: {service-name}`)
- SSL certificates stored in `/certs` directory for webhooks
- SageMaker jobs use IAM roles with appropriate permissions
- Model artifacts stored in S3 with versioning enabled
- Use SageMaker Python SDK for service integrations when possible

---

## Script Conventions

- When setting up an environment that requires installing additional packages, use a Python virtual environment (venv) or a container rather than modifying the system environment directly.
- Do NOT set executable file permissions (`chmod +x`) on scripts. Keep them at default `644`.
- Always invoke scripts through their interpreter explicitly:
  - Shell scripts: `bash script.sh`
  - Python scripts: `python3 script.py`
- Makefiles and docs should call scripts the same way (e.g. `bash scripts/setup.sh`), not as `./script.sh`.

### Running solution scripts

Each solution lives in its own top-level directory with a `requirements.txt`. Typical setup:

```bash
cd <solution_dir>
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 <main_script>.py ...
```

---

## Confidentiality

- Do NOT include any customer names in code, scripts, documentation, comments, commit messages, or any other content in this repository.
- Do NOT describe specific customer situations, use cases, or scenarios that could identify a customer.
- When a real-world example is needed, use generic placeholders (e.g. `example-customer`, `acme-corp`) or describe the scenario in general, anonymized terms.
- Review content before committing to ensure no customer-identifying information is present.

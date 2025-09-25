# Project Structure

## Directory Organization

### Active Projects
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

### Archived & Experimental
- **`_archived/`**: Deprecated or superseded implementations
- **`_experiments/`**: Proof-of-concept and experimental code

## Standard Project Layout

Each solution directory typically contains:

```
sagemaker_solution_name/
├── README.md              # Usage instructions and overview
├── Makefile              # Common operations (build, deploy, etc.)
├── main_script.py        # Primary implementation
├── requirements.txt      # Python dependencies
├── Dockerfile            # Container definition (for containerized solutions)
├── deployment.yaml       # Kubernetes manifests (for HyperPod EKS solutions)
├── job.sh               # Slurm job script (for HyperPod Slurm solutions)
├── train.py             # Training script (for Training Job solutions)
├── inference.py         # Inference script (for Endpoint solutions)
├── .gitignore           # Local ignores
└── test-data/           # Sample data or configurations
```

## Naming Conventions

### Directories
- Use underscores for separation: `hyperpod_eks_auto_node_taints`, `training_distributed_pytorch`
- Prefix with service type: 
  - `hyperpod_*` for HyperPod solutions
  - `training_*` for Training Job solutions
  - `inference_*` for Inference solutions
  - `sagemaker_*` for cross-service utilities
- Use descriptive names indicating functionality

### Files
- Python scripts: `snake_case.py`
- Kubernetes manifests: `kebab-case.yaml`
- Shell scripts: `kebab-case.sh`
- Documentation: `UPPERCASE.md` for main docs, `lowercase.md` for others
- Training scripts: `train.py`, `inference.py` for standard entry points

### Docker Images
- Repository: `{service-name}` (matches directory name without service prefix)
- Tag: `latest` for current version
- Full path: `842413447717.dkr.ecr.{region}.amazonaws.com/{service-name}:latest`

## Configuration Patterns

### HyperPod Solutions
- Use `provisioning_parameters.json` for HyperPod cluster configuration
- Store certificates in `certs/` subdirectory
- Use `lcc/` subdirectory for lifecycle scripts

### Training Solutions
- Use `hyperparameters.json` for training job parameters
- Store training data references in `data/` subdirectory
- Model artifacts output to S3 paths defined in configuration

### Inference Solutions
- Use `model.tar.gz` for model artifacts
- Store endpoint configuration in `endpoint_config.json`
- Use `code/` subdirectory for custom inference code

### General Patterns
- Place test data in `test-data/` subdirectory
- Store utilities in `utils/` subdirectory
- Use `requirements.txt` for Python dependencies
- Store IAM policies in `policies/` subdirectory
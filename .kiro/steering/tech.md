# Technology Stack

## Core Technologies

- **Python 3**: Primary language for scripts and utilities
- **Docker**: Containerization for deployments
- **Kubernetes**: Container orchestration via EKS
- **AWS SDK (boto3)**: AWS service integration
- **Slurm**: Job scheduling and workload management (HyperPod)

## SageMaker Services

- **AWS SageMaker HyperPod**: Managed distributed ML training infrastructure
- **SageMaker Training Jobs**: Managed training service with built-in algorithms
- **SageMaker Endpoints**: Real-time inference hosting
- **SageMaker Batch Transform**: Large-scale batch inference
- **SageMaker Processing**: Data processing and feature engineering
- **SageMaker Pipelines**: ML workflow orchestration

## Infrastructure

- **Amazon EKS**: Kubernetes service for container workloads
- **Amazon ECR**: Container registry (842413447717.dkr.ecr.{region}.amazonaws.com)
- **FSx Lustre**: High-performance file system
- **EFS**: Elastic file system for shared storage
- **S3**: Object storage for data and model artifacts

## Common Commands

### Docker Operations
```bash
# Build and push to ECR
make build        # Build Docker image
make login        # Login to ECR (or login-ecr)
make tag          # Tag image for ECR
make push         # Push to ECR registry
```

### Kubernetes Operations (HyperPod EKS)
```bash
make deploy       # Deploy to Kubernetes
make delete       # Remove deployment
make list-pods    # List running pods
make watch-logs   # Follow logs (or watch-logs-all)
```

### Slurm Operations (HyperPod Slurm)
```bash
make enqueue      # Submit job to Slurm queue
make alloc        # Allocate resources
make run          # Run with srun
make q            # Check queue status
make log          # Tail output logs
```

### SageMaker Operations
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

## Development Patterns

- Use Makefiles for common operations (especially HyperPod solutions)
- ECR repositories follow pattern: `{account}.dkr.ecr.{region}.amazonaws.com/{service}:latest`
- Python scripts use argparse for CLI interfaces
- Kubernetes deployments use consistent labeling (`app: {service-name}`)
- SSL certificates stored in `/certs` directory for webhooks
- SageMaker jobs use IAM roles with appropriate permissions
- Model artifacts stored in S3 with versioning enabled
- Use SageMaker Python SDK for service integrations when possible
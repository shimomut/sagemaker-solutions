# Product Overview

This repository contains AWS SageMaker solutions and utilities across the full spectrum of AI/ML capabilities. It provides practical implementations, automation scripts, and best practices for various SageMaker services.

## Key Components

### HyperPod Solutions
- **Cluster Management**: Scripts for creating, scaling, and deleting HyperPod clusters with retry logic and incremental scaling
- **EKS Integration**: Kubernetes deployments, webhooks, and utilities for HyperPod EKS clusters
- **Slurm Integration**: Job scheduling, auto-resume functionality, and multi-user management for HyperPod Slurm clusters

### Training Solutions
- **Training Jobs**: Utilities for SageMaker Training Jobs, including distributed training patterns
- **Model Training**: Custom training scripts, hyperparameter optimization, and experiment management

### Inference Solutions
- **Real-time Inference**: Endpoint deployment, auto-scaling, and monitoring utilities
- **Batch Inference**: Batch transform jobs and large-scale inference patterns
- **Multi-model Endpoints**: Solutions for hosting multiple models efficiently

### Shared Infrastructure
- **Storage Solutions**: FSx, EFS, and S3 integration patterns for distributed storage
- **Monitoring & Observability**: Health checks, profiling tools, and event handling
- **Infrastructure Utilities**: Network manipulation, SSSD configuration, and various operational tools

## Target Users

- ML Engineers working with SageMaker training and inference
- Data Scientists implementing ML workflows
- DevOps Engineers managing SageMaker infrastructure
- Solutions Architects implementing SageMaker deployments
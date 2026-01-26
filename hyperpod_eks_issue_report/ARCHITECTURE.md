# Architecture Overview

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         User's Machine                          │
│                                                                 │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │  hyperpod_eks_issue_report.py                             │ │
│  │  - Queries SageMaker API for cluster nodes                │ │
│  │  - Generates collection script                            │ │
│  │  - Orchestrates parallel execution                        │ │
│  └───────────────────────────────────────────────────────────┘ │
│                            │                                    │
└────────────────────────────┼────────────────────────────────────┘
                             │
                             ▼
              ┌──────────────────────────┐
              │      AWS Services        │
              │                          │
              │  ┌────────────────────┐  │
              │  │  SageMaker API     │  │
              │  │  - List nodes      │  │
              │  │  - Get cluster info│  │
              │  └────────────────────┘  │
              │                          │
              │  ┌────────────────────┐  │
              │  │  S3 Bucket         │  │
              │  │  - Store script    │  │
              │  │  - Store results   │  │
              │  └────────────────────┘  │
              │                          │
              │  ┌────────────────────┐  │
              │  │  SSM Service       │  │
              │  │  - Execute commands│  │
              │  └────────────────────┘  │
              └──────────────────────────┘
                             │
                             ▼
              ┌──────────────────────────┐
              │   HyperPod EKS Cluster   │
              │                          │
              │  ┌────────────────────┐  │
              │  │  Node 1            │  │
              │  │  - Download script │  │
              │  │  - Run commands    │  │
              │  │  - Upload results  │  │
              │  └────────────────────┘  │
              │                          │
              │  ┌────────────────────┐  │
              │  │  Node 2            │  │
              │  │  - Download script │  │
              │  │  - Run commands    │  │
              │  │  - Upload results  │  │
              │  └────────────────────┘  │
              │                          │
              │  ┌────────────────────┐  │
              │  │  Node N            │  │
              │  │  - Download script │  │
              │  │  - Run commands    │  │
              │  │  - Upload results  │  │
              │  └────────────────────┘  │
              └──────────────────────────┘
```

## Execution Flow

### Phase 1: Initialization
```
1. User runs hyperpod_eks_issue_report.py
2. Script queries SageMaker API for cluster nodes
3. Filters nodes by instance group (if specified)
4. Generates bash collection script with user commands
```

### Phase 2: Script Distribution
```
5. Upload collection script to S3
   s3://bucket/prefix/cluster/timestamp/collector_script.sh
```

### Phase 3: Parallel Execution
```
6. For each node (in parallel):
   a. Connect via SSM
   b. Download script from S3
   c. Execute script locally
   d. Script runs all commands
   e. Script creates tarball
   f. Script uploads tarball to S3
```

### Phase 4: Summary
```
7. Collect execution results from all nodes
8. Generate summary JSON
9. Upload summary to S3
10. Display statistics to user
```

## Data Flow

### Input
- Cluster name
- S3 bucket name
- Commands to execute
- Optional: instance group filter

### Processing
```
User Commands → Bash Script → S3 Upload
                                  ↓
                            SSM Distribution
                                  ↓
                         Parallel Execution
                                  ↓
                         Results Collection
                                  ↓
                            S3 Upload
```

### Output
```
S3 Structure:
s3://bucket/prefix/cluster/timestamp/
├── collector_script.sh          # Generated script
├── summary.json                 # Execution summary
└── results/
    ├── node1_timestamp.tar.gz   # Node 1 results
    ├── node2_timestamp.tar.gz   # Node 2 results
    └── nodeN_timestamp.tar.gz   # Node N results

Each tarball contains:
├── hostname.txt
├── timestamp.txt
├── command_01_<name>.txt
├── command_02_<name>.txt
└── command_NN_<name>.txt
```

## Component Responsibilities

### HyperPodEKSIssueReportCollector Class

**Methods:**
- `get_cluster_nodes()`: Query SageMaker for node list
- `generate_collector_script()`: Create bash script from commands
- `upload_collector_script()`: Upload script to S3
- `execute_collection_on_node()`: Execute via SSM on single node
- `collect_reports()`: Orchestrate parallel collection
- `save_summary()`: Generate and upload summary JSON

### Collector Script (Generated)

**Responsibilities:**
- Create output directory
- Execute each command
- Capture output to files
- Handle command failures gracefully
- Create tarball
- Upload to S3
- Clean up temporary files

## Concurrency Model

```
Main Thread
    │
    ├─→ ThreadPoolExecutor (max_workers=10)
    │       │
    │       ├─→ Worker 1: Node 1 → SSM → Execute
    │       ├─→ Worker 2: Node 2 → SSM → Execute
    │       ├─→ Worker 3: Node 3 → SSM → Execute
    │       └─→ Worker N: Node N → SSM → Execute
    │
    └─→ Collect Results → Generate Summary
```

## Security Considerations

### IAM Permissions Required

**User/Role Running Script:**
- `sagemaker:DescribeCluster`
- `sagemaker:ListClusterNodes`
- `ssm:StartSession`
- `s3:PutObject`
- `s3:GetObject`

**HyperPod Node IAM Role:**
- `s3:GetObject` (download script)
- `s3:PutObject` (upload results)
- `ssm:*` (SSM connectivity)

### Network Requirements
- Nodes must have SSM Agent running
- Nodes must have network access to S3
- Security groups must allow SSM traffic

## Scalability

### Horizontal Scaling
- Parallel execution across nodes
- Configurable worker pool size
- Independent node operations

### Performance Characteristics
- Time = max(node_execution_time) + overhead
- Overhead: ~10-30 seconds (API calls, script generation)
- Node execution: depends on commands
- Typical: 1-5 minutes for basic diagnostics

### Limitations
- SSM session timeout: 5 minutes per node
- S3 upload size: limited by node disk space
- Concurrent workers: default 10, configurable

## Error Handling

### Node-Level Failures
- Individual node failures don't stop collection
- Failed nodes reported in summary
- Partial results still collected

### Command-Level Failures
- Failed commands captured with error code
- Subsequent commands still execute
- All output preserved

### Network Failures
- Retry logic in AWS SDK
- Timeout handling for SSM sessions
- Graceful degradation

## Comparison with hyperpod_issue_report

### hyperpod_issue_report (Slurm-based)
- Uses SSH for connectivity
- Requires head node access
- Slurm-specific commands
- Direct file system access

### hyperpod_eks_issue_report (EKS-based)
- Uses SSM for connectivity
- No head node required
- Kubernetes-aware
- S3-based distribution and collection

## Extension Points

### Custom Commands
- Any shell command supported
- Multiple commands per execution
- Command output captured separately

### Custom Processing
- Extend `generate_collector_script()` for custom logic
- Add post-processing in `collect_reports()`
- Custom summary format in `save_summary()`

### Integration
- Can be called from other scripts
- Results parseable from S3
- Summary JSON for automation

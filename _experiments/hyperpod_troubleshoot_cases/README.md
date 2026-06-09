# HyperPod Troubleshoot Cases

Artificially reproduce common HyperPod failure scenarios so you can evaluate the
[SageMaker AI agent plugin](https://github.com/awslabs/agent-plugins/tree/main/plugins/sagemaker-ai)
troubleshooting skills end-to-end from an end-user point of view.

Each case has a **trigger** (breaks something) and a **revert** (restores it).
After triggering a case, ask the agent the matching prompt and observe whether
the skill diagnoses and remediates the issue correctly.

## Layout

```
hyperpod_troubleshoot_cases/
├── Makefile           # Top-level dispatcher
├── slurm/             # Slurm orchestrator cases (run on a head/login node)
└── eks/               # EKS orchestrator cases (run from a kubectl-configured workstation)
```

## Prerequisites

| Orchestrator | Where to run                                | Tools required                        |
|--------------|---------------------------------------------|---------------------------------------|
| Slurm        | HyperPod head node (or login node)          | `sbatch`, `scontrol`, `srun`, `ssh`   |
| EKS          | Workstation with `kubectl` pointing at HP   | `kubectl`, `aws`, `jq`                |

For node-level cases (GPU XID injection, disk fill) the script is uploaded to a
worker via SSM and executed there; the workstation needs the `aws` CLI and the
HyperPod cluster name exported as `HP_CLUSTER_NAME`.

## Quick start

```bash
make list                       # show every case
make slurm-case-1               # trigger Slurm case 1
make slurm-case-1-revert        # restore
make eks-case-1                 # trigger EKS case 1
make eks-case-1-revert          # restore
```

## Slurm cases

| #  | Name                       | Trigger summary                                   | Skill being tested                  | Suggested agent prompt                                          |
|----|----------------------------|---------------------------------------------------|-------------------------------------|------------------------------------------------------------------|
| 1  | node-drain                 | `scontrol update nodename=… state=drain`          | `hyperpod-slurm-debugger`           | "A Slurm node is stuck in drain state, diagnose it"             |
| 2  | stuck-pending              | Submit a job needing more GPUs than the cluster   | `hyperpod-slurm-debugger`           | "Slurm job is stuck PENDING with REASON=Resources, why?"        |
| 3  | gpu-xid-inject             | Inject XID 94 via `dcgmi test --inject` on node   | `hyperpod-node-debugger`            | "GPU on node X is reporting hardware errors, investigate"       |
| 4  | disk-pressure              | Fill `/var/log` to ≥ 95 % on a node               | `hyperpod-node-debugger`            | "A worker node is unresponsive, check it"                       |
| 5  | nccl-hang                  | Multi-node NCCL job with mismatched world size    | `hyperpod-nccl`                     | "Training job hangs at NCCL AllReduce, help me debug"           |

## EKS cases

| #  | Name                        | Trigger summary                                   | Skill being tested                  | Suggested agent prompt                                          |
|----|-----------------------------|---------------------------------------------------|-------------------------------------|------------------------------------------------------------------|
| 1  | pod-oom                     | Pod requests 64 MiB, allocates 256 MiB → OOMKilled | `hyperpod-nccl`                    | "My pod keeps getting OOMKilled, diagnose it"                   |
| 2  | crashloopbackoff            | Pod whose entrypoint exits 1 → CrashLoopBackOff   | `hyperpod-nccl`                     | "A pod is stuck in CrashLoopBackOff, what's wrong?"             |
| 3  | pending-unschedulable       | Pod requests 999 `nvidia.com/gpu`                 | `hyperpod-nccl` / cluster-debugger  | "My GPU pod is stuck Pending, why?"                             |
| 4  | nccl-hang                   | Two-pod NCCL AllReduce with bad MASTER_ADDR       | `hyperpod-nccl`                     | "Multi-node NCCL training hangs at init, help"                  |
| 5  | networkpolicy-block         | Apply a default-deny NetworkPolicy on the ns      | `hyperpod-nccl`                     | "Pods can't reach each other, NCCL rendezvous fails"            |

## Workflow per case

1. Confirm the cluster is healthy first:
   ```bash
   make sanity-check ORCH=slurm   # or eks
   ```
2. Trigger the case:
   ```bash
   make slurm-case-3
   ```
3. Open a fresh Claude Code session and feed the **suggested agent prompt** from
   the table above. Don't volunteer extra context — the goal is to evaluate the
   skill end-to-end.
4. Record what the agent did (which skill was loaded, what it inspected, what
   remediation it proposed).
5. Revert:
   ```bash
   make slurm-case-3-revert
   ```

## Safety notes

- Cases that actually disrupt nodes (XID injection, disk fill) are gated behind
  `CONFIRM=1` because they can lead to HyperPod's auto-recovery rebooting or
  replacing the node. **Do not run on a shared production cluster.**
- Each `*-revert` target is best-effort; if the cluster's health daemon already
  rebooted/replaced a node, the revert is a no-op.
- All triggers default to dry-run mode. You must pass `CONFIRM=1` to actually
  break something.

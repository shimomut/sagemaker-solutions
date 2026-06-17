# Mountpoint for S3 CSI Driver — Local Cache on SageMaker HyperPod EKS

## Overview

This guide demonstrates how to configure the **Mountpoint for Amazon S3 CSI driver** with **local NVMe caching** on a SageMaker HyperPod EKS cluster. Local caching accelerates repeated reads from S3 by storing hot data on instance-local NVMe SSDs, which is particularly useful for ML training workloads that iterate over the same dataset multiple times.

### What you'll achieve

1. S3 objects cached on instance-local NVMe for fast repeated access
2. A setup that survives HyperPod node auto-recovery (no manual re-provisioning needed)
3. Minimal per-workload configuration

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│  Training Pod                                           │
│  ┌───────────────────────────────────────────────────┐  │
│  │  volumeMount: /data (S3 bucket via Mountpoint)    │  │
│  └───────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────┐
│  Mountpoint for S3 CSI Driver (s3.csi.aws.com)          │
│  ┌───────────────────────────────────────────────────┐  │
│  │  Local Cache: emptyDir or ephemeral volume        │  │
│  │  Backed by: NVMe instance store                   │  │
│  └───────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────┐
│  Amazon S3 (same region/AZ as compute)                  │
└─────────────────────────────────────────────────────────┘
```

## Background: How NVMe is Configured on HyperPod EKS

The HyperPod EKS lifecycle script (`on_create_main.sh`) relocates kubelet's (and containerd's) data root to a chosen disk at node creation time. The disk is selected at the **top of the script**:

```bash
# From the default lifecycle script (lines ~8-9):
DISK_FOR_CONTAINERD_KUBELET="/opt/sagemaker"      # DEFAULT: secondary EBS volume
#DISK_FOR_CONTAINERD_KUBELET="/opt/dlami/nvme"    # alternative: local NVMe instance store
```

Later in the script, kubelet's data root is symlinked onto that disk:

```bash
mkdir -p "$DISK_FOR_CONTAINERD_KUBELET/kubelet"
mv /var/lib/kubelet/* "$DISK_FOR_CONTAINERD_KUBELET/kubelet/"
rmdir /var/lib/kubelet
ln -s "$DISK_FOR_CONTAINERD_KUBELET/kubelet" /var/lib/
```

> **Important:** By **default** this points at `/opt/sagemaker`, which is the **secondary EBS volume — not NVMe**. Because Kubernetes `emptyDir` volumes live under `/var/lib/kubelet/pods/<pod-id>/volumes/kubernetes.io~empty-dir/`, an `emptyDir` cache lands on **whatever disk `DISK_FOR_CONTAINERD_KUBELET` points to**. To back the cache with local NVMe (Option A), you must edit the script to use `/opt/dlami/nvme` (see Option A, Step 0).
>
> **Node recreation required:** The lifecycle script only runs when a node is **created**. After editing it, you must **recreate / replace the affected nodes** for the change to take effect — **rebooting an existing node is not sufficient**, since the script does not re-run on reboot.

Reference: [HyperPod EKS Lifecycle Script](https://github.com/awslabs/awsome-distributed-ai/blob/main/1.architectures/7.sagemaker-hyperpod-eks/LifecycleScripts/base-config/on_create_main.sh)

### How the DLAMI exposes the instance-store NVMe

Observed on an `ml.g6.8xlarge` node (verify yours via SSM with `lsblk` / `mount`):

- The instance has **two** local NVMe instance-store disks (model `Amazon EC2 NVMe Instance Storage`).
- The DLAMI's `dlami-nvme.service` aggregates them with **LVM** into one volume group (`vg.01` → `lv_ephemeral`) formatted **ext4** and mounted at **`/opt/dlami/nvme`** (≈838 GB).
- Under the default lifecycle config, kubelet/containerd live on `/opt/sagemaker` (EBS), so **`/opt/dlami/nvme` is essentially empty and available**.

Two consequences shape the options below:

1. The NVMe disks are **not raw block devices** — they are LVM members inside a mounted filesystem. So the Local Volume Static Provisioner's *device/raw* mode (and udev symlinks under `/dev/disk/kubernetes`) **does not apply** to the HyperPod DLAMI. Option B therefore uses the provisioner's **filesystem / `hostDir`** mode against `/opt/dlami/nvme`.
2. The DLAMI already gives you a ready-to-use NVMe filesystem, so **Option B needs no lifecycle-script change and no node recreation** — it only adds Kubernetes-side components.

## Approach Options

| Option | Cache Type | Backing Storage | Pros | Cons |
|--------|-----------|-----------------|------|------|
| **A** | `emptyDir` | NVMe via kubelet data-root relocation | Simplest architecture; no extra cluster components | Requires a lifecycle-script change + a one-time node recreation; the cache shares the NVMe pool with kubelet, containerd, and every other `emptyDir` |
| **B** | `ephemeral` + Local Volume Static Provisioner (`hostDir` mode) | A bind-mounted directory on the DLAMI NVMe (`/opt/dlami/nvme`) | **No lifecycle edit / no node recreation**; kubelet/containerd stay on EBS so the NVMe is dedicated to caching | More moving parts (privileged setup DaemonSet + provisioner + StorageClass + cleanup controller) |

### Which option is easier?

It depends on whether you can recreate nodes:

| Aspect | Option A (`emptyDir`) | Option B (`hostDir` ephemeral) |
|--------|-----------------------|--------------------------------|
| Lifecycle script edit | Required (`DISK_FOR_CONTAINERD_KUBELET`) | Not required |
| Node recreation | **Required** (reboot is not enough) | Not required |
| Extra cluster components | None | Setup DaemonSet + provisioner + StorageClass |
| kubelet/containerd storage | Moves onto NVMe | Stays on EBS |
| Failure surface | Minimal | Higher (privileged bind-mounting DaemonSet) |

- **Choose Option A** if you're willing to recreate the affected nodes at least once (it needn't be a routine practice). It has the simplest runtime architecture — no add-on controllers — in exchange for a lifecycle-script change plus a one-time node recreation.
- **Choose Option B** if you cannot disrupt running nodes, or want kubelet/containerd to stay on EBS while the cache uses NVMe.

> **NVMe is a shared pool with no hard capacity isolation.** The DLAMI aggregates a node's instance-store NVMe into a single `/opt/dlami/nvme` filesystem. Everything that uses it — kubelet, containerd, `emptyDir` caches (Option A), or the Option B cache PVs — draws from that one pool, and there's no enforced per-consumer quota, so any single consumer can fill it. Decide per instance group which option that group uses: on one NVMe pool, use **either** Option A **or** Option B, not both, since they would contend for the same space. (Option A's `cacheEmptyDirSizeLimit` and Option B's ephemeral storage request set *soft* caps on the cache itself, but they don't hard-partition the filesystem.)

## Prerequisites

- SageMaker HyperPod EKS cluster (running)
- Mountpoint for S3 CSI driver add-on installed
- IAM role with S3 bucket access (via IRSA or EKS Pod Identity)
- Instance types with NVMe instance store (e.g., p5, p5e, p5en, p6e, g6 — required for the local cache)

---

## Option A: `emptyDir` Cache (Recommended Starting Point)

This is the simplest approach: an `emptyDir` cache backed by local NVMe. It does not need a provisioner, but it **does require the kubelet data root to live on NVMe**, which is *not* the default (see Background).

### Step 0: Point kubelet's data root at NVMe (lifecycle script)

Option A requires kubelet's data root to live on NVMe, which is *not* the default (see Background). Use the helper script, which edits `on_create_main.sh` in the cluster's LCC S3 bucket for you:

```bash
make lcc-set-auto HYPERPOD_CLUSTER_NAME=<your-hp-cluster>
# or directly:
#   python3 scripts/update_lifecycle_nvme.py --cluster-name <your-hp-cluster> --target auto
```

This replaces the static `DISK_FOR_CONTAINERD_KUBELET=...` line with a small, marked block that decides **at node-creation time**:

- If the instance **has** local instance-store NVMe → use `/opt/dlami/nvme`. It waits (up to `NVME_WAIT_SECONDS`, default 120s) for `dlami-nvme.service` to finish mounting NVMe before deciding, so it doesn't race the mount.
- If the instance has **no** instance-store NVMe → fall back to `/opt/sagemaker` (secondary EBS).

So the same lifecycle script is safe across NVMe and non-NVMe instance types. Other modes:

```bash
make lcc-set-nvme    # force /opt/dlami/nvme (no fallback)
make lcc-revert-ebs  # force /opt/sagemaker (revert to the EBS default)
```

The original script is backed up locally under `.lcc-backup/<timestamp>/` before each change, and edits are idempotent (wrapped in sentinel markers).

Then **recreate the affected nodes** so the updated script runs:

- The lifecycle script executes **only at node creation**. Rebooting an existing node does **not** re-run it.
- Use the automation (replaces nodes via `BatchReplaceClusterNodes`, keeping the group's instance count):

  ```bash
  make lcc-replace-nodes HYPERPOD_CLUSTER_NAME=<your-hp-cluster> NVME_INSTANCE_GROUP=<group>
  # add CONFIRM=yes to skip the interactive prompt
  ```

  This is **destructive** — the targeted nodes are terminated and reprovisioned. After recreation, verify on a node via SSM that `/var/lib/kubelet` is a symlink onto `/opt/dlami/nvme`.

> On instances **without** NVMe instance store, the `auto` mode leaves the cache on the secondary EBS volume — functional, just not NVMe-accelerated.

### Step 1: Install Mountpoint S3 CSI Driver

These steps follow the [Set up an Amazon S3 mountpoint](https://awslabs.github.io/ai-on-sagemaker-hyperpod/docs/eks-orchestration/getting-started/Set%20up%20an%20Amazon%20S3%20mountpoint) walkthrough on the *AI on SageMaker HyperPod* workshop site. The CSI driver supports **static provisioning only** — it does not create buckets.

```bash
export EKS_CLUSTER_NAME=<your-cluster-name>
export AWS_REGION=<your-region>
export S3_BUCKET_NAME=<your-bucket-name>
```

**1. Associate an IAM OIDC provider with the cluster**

```bash
eksctl utils associate-iam-oidc-provider --cluster $EKS_CLUSTER_NAME --approve
```

**2. Create an IAM policy for S3 access**

```bash
cat <<EOF > s3accesspolicy.json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "MountpointFullBucketAccess",
      "Effect": "Allow",
      "Action": ["s3:ListBucket"],
      "Resource": ["arn:aws:s3:::${S3_BUCKET_NAME}"]
    },
    {
      "Sid": "MountpointFullObjectAccess",
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject",
        "s3:AbortMultipartUpload",
        "s3:DeleteObject"
      ],
      "Resource": ["arn:aws:s3:::${S3_BUCKET_NAME}/*"]
    }
  ]
}
EOF

aws iam create-policy \
  --policy-name S3MountpointAccessPolicy \
  --policy-document file://s3accesspolicy.json
```

> For a read-only caching workload you can drop `s3:PutObject`, `s3:AbortMultipartUpload`, and `s3:DeleteObject`, and use `read-only` in the PV `mountOptions` (as shown below).

**3. Create the IAM role (role only) bound to the CSI service account**

```bash
export S3_CSI_ROLE_NAME=SM_HP_S3_CSI_ROLE
POLICY_ARN=$(aws iam list-policies \
  --query 'Policies[?PolicyName==`S3MountpointAccessPolicy`].Arn' \
  --output text)

eksctl create iamserviceaccount \
  --name s3-csi-driver-sa \
  --namespace kube-system \
  --cluster $EKS_CLUSTER_NAME \
  --attach-policy-arn $POLICY_ARN \
  --approve \
  --role-name $S3_CSI_ROLE_NAME \
  --region $AWS_REGION \
  --role-only
```

**4. Install the CSI driver add-on**

```bash
ROLE_ARN=$(aws iam get-role --role-name $S3_CSI_ROLE_NAME --query 'Role.Arn' --output text)

eksctl create addon \
  --name aws-mountpoint-s3-csi-driver \
  --cluster $EKS_CLUSTER_NAME \
  --service-account-role-arn $ROLE_ARN \
  --force
```

Verify the driver is running:

```bash
kubectl get pods -n kube-system -l app=s3-csi-node
kubectl get csidrivers | grep s3
```

### Step 2: Create the PV (emptyDir cache) + PVC

```bash
make deploy-a S3_BUCKET_NAME=<your-bucket>
```

This renders `manifests/pv-option-a.yaml` and `manifests/pvc.yaml` and applies them. The PV's cache attributes are:

```yaml
    volumeAttributes:
      bucketName: <YOUR-BUCKET-NAME>
      cache: emptyDir
      cacheEmptyDirSizeLimit: 100Gi   # soft cap — set this to avoid filling the node's NVMe
      # cacheEmptyDirMedium: ""       # default = disk; NVMe only when Step 0 put kubelet on /opt/dlami/nvme
```

Bucket, cache size, PV/PVC names, namespace, etc. are Makefile variables (see the top of the `Makefile`).

### Step 3: Launch a test pod and verify

```bash
make deploy-test-pod S3_BUCKET_NAME=<your-bucket>
make verify-mount      # ls + df of /data inside the pod
```

To confirm the cache is NVMe-backed, on the node (via SSM):

```bash
ls -la /var/lib/kubelet     # should be a symlink to /opt/dlami/nvme/kubelet (after Step 0)
df -h /opt/dlami/nvme       # usage rises as the cache fills during reads
```

To mount the bucket in your own workload, reference the PVC (`s3-training-data-pvc` by default) as a read-only volume — see `manifests/test-pod.yaml` for a template.

---

## Option B: `ephemeral` Cache on the DLAMI NVMe (hostDir mode)

Use this when you **can't recreate nodes** or want kubelet/containerd to stay on EBS while the S3 cache uses NVMe. It requires **no lifecycle-script change and no node recreation** — everything is deployed into the cluster.

Because the DLAMI aggregates the instance-store NVMe into a single ext4 filesystem at `/opt/dlami/nvme` (see Background), this option uses the Local Volume Static Provisioner in **filesystem / `hostDir` mode**, not raw-device mode. The flow is:

```
/opt/dlami/nvme (DLAMI NVMe fs)
   └── s3-cache-src/vol1..N        (subdirectories)
         │  bind-mounted by the setup DaemonSet
         ▼
/mnt/s3-cache-disks/vol1..N        (discovery dir, one mount point per PV)
         │  discovered by the Local Volume Static Provisioner
         ▼
PersistentVolumes in StorageClass "nvme-cache"
         │  bound to the S3 CSI driver's ephemeral cache PVC
         ▼
Mountpoint Pod uses the NVMe-backed volume as local cache
```

> **Why a setup DaemonSet?** The provisioner only discovers *mount points* in filesystem mode. A privileged DaemonSet (`nvme-cache-setup`) creates subdirectories on `/opt/dlami/nvme` and **bind-mounts** them into the discovery directory at runtime — so you avoid editing the lifecycle script. The pod re-creates the bind mounts on restart, so they survive reboots.

### Step 1: Install the CSI driver

Same as Option A, Step 1 (the driver install is identical).

### Step 2: Deploy the setup DaemonSet + provisioner + cleanup controller

```bash
# Adjust the nodeSelector in nvme-cache-setup-daemonset.yaml to your NVMe instance type first.
make install-nvme-cache
# equivalent to:
#   kubectl apply -f manifests/nvme-cache-setup-daemonset.yaml
#   kubectl apply -f manifests/nvme-cache-provisioner.yaml
#   kubectl apply -f manifests/nvme-cache-node-cleanup.yaml
```

This deploys three things:
- **`nvme-cache-setup`** DaemonSet — bind-mounts cache directories on `/opt/dlami/nvme`.
- **Local Volume Static Provisioner** — publishes those as `nvme-cache` PVs.
- **Local Volume Node Cleanup Controller** (`registry.k8s.io/sig-storage/local-volume-node-cleanup:v2.8.0`) — automatically deletes orphaned `nvme-cache` PVs when a node is removed, so stale PVs don't accumulate (see Known limitations).

Verify the local PVs were published (one per `vol` per node):

```bash
kubectl -n kube-system get pods -l app=nvme-cache-setup
kubectl -n kube-system get pods -l app.kubernetes.io/name=local-static-provisioner
kubectl -n kube-system get pods -l app=local-volume-node-cleanup
kubectl get pv | grep nvme-cache   # expect Available PVs in StorageClass nvme-cache
```

### Step 3: Create the PV (ephemeral cache) + PVC

```bash
make deploy-b S3_BUCKET_NAME=<your-bucket>
```

This renders `manifests/pv-option-b.yaml` and `manifests/pvc.yaml`. The PV's cache attributes are:

```yaml
    volumeAttributes:
      bucketName: <YOUR-BUCKET-NAME>
      cache: ephemeral
      cacheEphemeralStorageClassName: nvme-cache
      cacheEphemeralStorageResourceRequest: 100Gi
```

When a workload mounts the PVC, the S3 CSI driver creates an ephemeral PVC in `nvme-cache`; with `WaitForFirstConsumer` it binds to a local PV on the node where the Mountpoint Pod is scheduled.

### Step 4: Verify on the node (via SSM)

```bash
# The setup DaemonSet's bind mounts
mount | grep s3-cache-disks
ls -la /mnt/s3-cache-disks/

# The backing NVMe filesystem
df -h /opt/dlami/nvme
```

> **Capacity note:** All PVs that share the `/opt/dlami/nvme` filesystem report the full filesystem size and have **no hard capacity isolation** between them. The cache footprint is still bounded by `cacheEphemeralStorageResourceRequest` and Mountpoint's own cache management, but sizing should assume the volumes share one pool. For true isolation you would need separate partitions/LVs, which means lifecycle-script surgery (defeating Option B's no-recreation benefit).


---

## Auto-Recovery Behavior

| Component | Survives Node Replacement? | Why |
|-----------|---------------------------|-----|
| Mountpoint CSI driver | ✅ | Installed as EKS add-on (cluster-level) |
| kubelet NVMe symlink (Option A) | ✅ | Lifecycle script (with Step 0 edit) re-runs on new node |
| `emptyDir` / `ephemeral` cache data | ❌ (cold start) | Cache is ephemeral — rebuilds on first access |
| DLAMI `/opt/dlami/nvme` mount | ✅ | `dlami-nvme.service` re-creates the LVM mount at boot |
| Bind mounts (Option B) | ✅ | `nvme-cache-setup` DaemonSet re-creates them on the new node |
| Static Provisioner PVs (Option B) | ✅ | DaemonSet re-discovers the bind-mounted dirs |

**Key point:** The cache data itself is always ephemeral — after a node replacement, the first read from S3 populates the cache. Subsequent reads are served from local storage. This is expected behavior and does not require manual intervention.

---

## Validation Results

This guide was validated end-to-end on a live SageMaker HyperPod EKS cluster.

**Environment**
- GPU instances (e.g. `ml.g6.8xlarge`): instance-store NVMe disk(s) that the DLAMI's `dlami-nvme.service` aggregates via LVM into one ext4 filesystem at `/opt/dlami/nvme`.
- CPU instances (e.g. `ml.m5.xlarge`): no instance-store NVMe (EBS only).
- Mountpoint for Amazon S3 CSI driver add-on; a test bucket containing a large object plus smaller files.

**Lifecycle `auto` script** (`scripts/update_lifecycle_nvme.py --target auto`) — verified by replacing nodes via `BatchReplaceClusterNodes`:

| Node type | Instance-store NVMe? | Result after recreation |
|-----------|----------------------|--------------------------|
| GPU (e.g. `ml.g6.8xlarge`) | Yes | `/var/lib/kubelet -> /opt/dlami/nvme/kubelet`; containerd data-root + pod volumes on NVMe |
| CPU (e.g. `ml.m5.xlarge`) | No | fell back to `/var/lib/kubelet -> /opt/sagemaker/kubelet` (EBS) |

All nodes rejoined `Ready` with no lifecycle errors, confirming the same script is safe on both NVMe and non-NVMe instance types.

**Cache behavior** — repeated reads of the same object from a pod:

| Option | Cache location (verified) |
|--------|---------------------------|
| **A** (`emptyDir`) | the Mountpoint pod's `--cache=/local-cache` resolved onto the node's kubelet dir on `/opt/dlami/nvme` (NVMe) |
| **B** (`ephemeral` / hostDir) | `/local-cache` backed by an `nvme-cache` local PV on `/opt/dlami/nvme` (NVMe) |

In both cases the first (cold) read populated the cache and subsequent (warm) reads were served from local NVMe — verified on-node by watching `/opt/dlami/nvme` usage grow as the cache filled.

**Auto-configuration on new nodes** — verified by replacing a g6 node (with both solutions deployed) and inspecting the brand-new instance. With no manual steps it came up fully configured:

| Solution | What happened automatically on the new node |
|----------|----------------------------------------------|
| **A** | The `auto` lifecycle script ran and relocated kubelet onto NVMe (`/var/lib/kubelet -> /opt/dlami/nvme/kubelet`) |
| **B** | `nvme-cache-setup` + `local-static-provisioner` DaemonSets scheduled onto it, bind mounts were created, and the provisioner published fresh `nvme-cache` PVs for the node |

A scaled-up node runs the identical bootstrap path (same `on_create.sh` + DaemonSets schedule onto it), so it configures the same way. (A literal scale-up was constrained by instance-type quota in the test account, so a node replacement was used to exercise the same new-node path.)

**Node Cleanup Controller on real node replacement (Option B)** — with the provisioner, setup DaemonSet, and Node Cleanup Controller deployed, one g6 node was replaced:

- Baseline 8 `nvme-cache` PVs (4 per g6 node).
- When the replaced node left the cluster, the controller **automatically deleted its 4 orphaned PVs** (logs: `Attempting to delete PV that has NodeAffinity to deleted Node`) → 4 PVs remained, no manual prune.
- The new node joined and the provisioner published 4 fresh PVs → back to 8, zero orphans.
- The new node also confirmed the EBS lifecycle mode (`/var/lib/kubelet -> /opt/sagemaker/kubelet`).

### Known limitations (Option B)

Applies to Option B only; Option A is unaffected.

- **`nodeSelector` is instance-type-specific.** `manifests/nvme-cache-setup-daemonset.yaml` targets `node.kubernetes.io/instance-type: ml.g6.8xlarge`. Scaling up a *different* NVMe instance type won't auto-configure Option B until you broaden that selector (or switch to a label-based selector covering all your NVMe instance types). Option A has no such limitation — its lifecycle logic auto-detects NVMe on any instance type.

### Orphaned PV cleanup (Option B)

The static provisioner creates cluster-scoped `PersistentVolume` objects pinned to a node. Left unmanaged, a replaced/removed node would leave its `nvme-cache` PVs behind as `Available` with node-affinity to a node that no longer exists (the provisioner only reclaims a PV when its *bound* PVC is released). This is handled automatically: `make install-nvme-cache` deploys the **Local Volume Node Cleanup Controller** (`manifests/nvme-cache-node-cleanup.yaml`), which on each node deletion removes that node's orphaned `nvme-cache` PVs. It deletes only the PV/PVC API objects, not data — instance-store data is already lost when the node goes away. (Option A has no PV objects, so there's nothing to clean up.)

If you opt not to run the controller, clean up on demand instead (a PV is treated as orphaned only when it is in the `nvme-cache` StorageClass, `Available`, and pinned to a node that no longer exists):

```bash
make list-orphaned-pvs    # dry run — list orphaned nvme-cache PVs
make prune-orphaned-pvs   # delete them
```

Example:

```text
$ make list-orphaned-pvs
Orphaned 'nvme-cache' PVs (Available, node no longer exists):
  - local-pv-1fbd28fc  (pinned to: <node-that-was-removed>)
1 orphan(s). Re-run with --delete to remove them.
```

---

## Performance Considerations

- **`metadata-ttl indefinite`** — Use when training data doesn't change during a job. Eliminates S3 HEAD requests for metadata.
- **`cacheEmptyDirSizeLimit`** — Always set this to prevent the cache from consuming all node storage.
- **S3 bucket locality** — Ensure the bucket is in the same region (and same AZ for S3 Express One Zone) as compute nodes.
- **Read patterns** — Local cache benefits sequential re-reads most (e.g., multi-epoch training). Random one-time reads see minimal benefit.

---

## Troubleshooting

```bash
# Check if Mountpoint pod is running for your volume
kubectl get pods -n kube-system -l app=s3-csi-node

# Describe the Mountpoint pod for errors
kubectl describe pod <mountpoint-pod-name> -n kube-system

# Check PV/PVC binding
kubectl get pv,pvc

# On-node: check if NVMe is properly mounted
# (via SSM session)
lsblk
df -h
ls -la /var/lib/kubelet  # should be symlink

# Check cache usage (Option A - emptyDir)
du -sh /var/lib/kubelet/pods/*/volumes/kubernetes.io~empty-dir/

# Check cache setup (Option B - hostDir bind mounts)
kubectl -n kube-system logs -l app=nvme-cache-setup --tail=20
mount | grep s3-cache-disks          # on the node, via SSM
kubectl get pv | grep nvme-cache     # expect Available/Bound PVs

# Check Mountpoint logs
kubectl logs <mountpoint-pod-name> -n kube-system
```

---

## References

- [Mountpoint S3 CSI Driver — Caching Configuration](https://github.com/awslabs/mountpoint-s3-csi-driver/blob/main/docs/CACHING.md)
- [Mountpoint S3 CSI Driver — General Configuration](https://github.com/awslabs/mountpoint-s3-csi-driver/blob/main/docs/CONFIGURATION.md)
- [AI on SageMaker HyperPod workshop — Set up an Amazon S3 mountpoint](https://awslabs.github.io/ai-on-sagemaker-hyperpod/docs/eks-orchestration/getting-started/Set%20up%20an%20Amazon%20S3%20mountpoint)
- [HyperPod EKS Lifecycle Script](https://github.com/awslabs/awsome-distributed-ai/blob/main/1.architectures/7.sagemaker-hyperpod-eks/LifecycleScripts/base-config/on_create_main.sh)
- [Local Volume Static Provisioner](https://github.com/kubernetes-sigs/sig-storage-local-static-provisioner)
- [Local Volume Static Provisioner — Operations (hostDir / bind-mount mechanics)](https://github.com/kubernetes-sigs/sig-storage-local-static-provisioner/blob/master/docs/operations.md)
- [Mountpoint for Amazon S3 — Open Source File Client](https://aws.amazon.com/s3/features/mountpoint/)

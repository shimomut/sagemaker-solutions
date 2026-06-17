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
│  Mountpoint for S3 CSI Driver (s3.csi.aws.com)         │
│  ┌───────────────────────────────────────────────────┐  │
│  │  Local Cache: emptyDir or ephemeral volume        │  │
│  │  Backed by: NVMe instance store                   │  │
│  └───────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────┐
│  Amazon S3 (same region/AZ as compute)                 │
└─────────────────────────────────────────────────────────┘
```

## Background: How NVMe is Configured on HyperPod EKS

The HyperPod EKS lifecycle script (`on_create_main.sh`) relocates kubelet's data root to NVMe or secondary EBS at node creation time:

```bash
# From the default lifecycle script (lines ~118-133):
DISK_FOR_CONTAINERD_KUBELET="/opt/dlami/nvme"  # or "/opt/sagemaker"

mkdir -p "$DISK_FOR_CONTAINERD_KUBELET/kubelet"
mv /var/lib/kubelet/* "$DISK_FOR_CONTAINERD_KUBELET/kubelet/"
rmdir /var/lib/kubelet
ln -s "$DISK_FOR_CONTAINERD_KUBELET/kubelet" /var/lib/
```

This means all Kubernetes `emptyDir` volumes physically reside on the NVMe-backed path, since emptyDir is stored under `/var/lib/kubelet/pods/<pod-id>/volumes/kubernetes.io~empty-dir/`.

Reference: [HyperPod EKS Lifecycle Script](https://github.com/awslabs/awsome-distributed-ai/blob/main/1.architectures/7.sagemaker-hyperpod-eks/LifecycleScripts/base-config/on_create_main.sh)

## Approach Options

| Option | Cache Type | Backing Storage | Pros | Cons |
|--------|-----------|-----------------|------|------|
| **A** | `emptyDir` | NVMe via kubelet symlink | Simple; survives auto-recovery; no extra provisioner | Shares NVMe with containerd/other pods; no size guarantee |
| **B** | `ephemeral` + Local Volume Static Provisioner | Dedicated NVMe partition | Isolated cache volume; predictable performance | Requires provisioner + udev rules + StorageClass |

## Prerequisites

- SageMaker HyperPod EKS cluster (running)
- Mountpoint for S3 CSI driver add-on installed
- IAM role with S3 bucket access (via IRSA or EKS Pod Identity)
- Instance types with NVMe instance store (e.g., p5, p5e, p5en, p6e, g6 — required for the local cache)

---

## Option A: `emptyDir` Cache (Recommended Starting Point)

This is the simplest approach. It leverages the existing HyperPod lifecycle script that already symlinks kubelet to NVMe.

### Step 1: Install Mountpoint S3 CSI Driver

These steps follow the official [HyperPod EKS — Set up an Amazon S3 Mountpoint](https://awslabs.github.io/ai-on-sagemaker-hyperpod/docs/eks-orchestration/getting-started/Set%20up%20an%20Amazon%20S3%20mountpoint) guide. The CSI driver supports **static provisioning only** — it does not create buckets.

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

### Step 2: Create PersistentVolume with emptyDir Cache

```yaml
# pv-s3-cached.yaml
apiVersion: v1
kind: PersistentVolume
metadata:
  name: s3-training-data-pv
spec:
  capacity:
    storage: 1200Gi  # ignored, required by K8s
  accessModes:
    - ReadOnlyMany
  mountOptions:
    - region <REGION>
    - read-only
    - metadata-ttl indefinite  # cache metadata indefinitely for repeated reads
  storageClassName: ""
  claimRef:
    namespace: default
    name: s3-training-data-pvc
  csi:
    driver: s3.csi.aws.com
    volumeHandle: s3-training-data-volume  # must be unique per PV
    volumeAttributes:
      bucketName: <YOUR-BUCKET-NAME>

      # Local cache configuration
      cache: emptyDir
      cacheEmptyDirSizeLimit: 500Gi  # IMPORTANT: set a limit to avoid filling the node
      # cacheEmptyDirMedium: ""      # default = disk (NVMe via lifecycle script symlink)
```

### Step 3: Create PersistentVolumeClaim

```yaml
# pvc-s3-cached.yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: s3-training-data-pvc
spec:
  accessModes:
    - ReadOnlyMany
  storageClassName: ""
  resources:
    requests:
      storage: 1200Gi  # ignored, required by K8s
  volumeName: s3-training-data-pv
```

### Step 4: Mount in Training Pod

```yaml
# training-pod.yaml
apiVersion: v1
kind: Pod
metadata:
  name: training-job
spec:
  containers:
    - name: trainer
      image: <YOUR-TRAINING-IMAGE>
      command: ["python", "train.py", "--data-dir", "/data"]
      volumeMounts:
        - name: training-data
          mountPath: /data
          readOnly: true
  volumes:
    - name: training-data
      persistentVolumeClaim:
        claimName: s3-training-data-pvc
```

### Step 5: Apply and Verify

```bash
kubectl apply -f pv-s3-cached.yaml
kubectl apply -f pvc-s3-cached.yaml
kubectl apply -f training-pod.yaml

# Verify the mount and cache are working
kubectl exec -it training-job -- ls /data/
kubectl exec -it training-job -- df -h

# On the node (via SSM), verify NVMe is backing kubelet
ls -la /var/lib/kubelet  # should be a symlink to NVMe path
df -h | grep nvme
```

---

## Option B: `ephemeral` Cache with Local Volume Static Provisioner (Dedicated NVMe)

Use this when you need an isolated, dedicated NVMe volume for S3 caching — separate from kubelet and containerd storage.

### Step 1: Add udev Rules to Lifecycle Script

Add the following to your HyperPod lifecycle script (`on_create_main.sh`):

```bash
# === Dedicated NVMe for S3 Cache ===
# Create udev rules to discover NVMe instance store devices
cat << 'EOF' > /etc/udev/rules.d/90-kubernetes-discovery.rules
KERNEL=="nvme[0-9]*n[0-9]*", ENV{DEVTYPE}=="disk", ATTRS{model}=="Amazon EC2 NVMe Instance Storage", SYMLINK+="disk/kubernetes/nvme%n"
EOF

udevadm control --reload-rules
udevadm trigger

# Format and mount a dedicated NVMe device for cache
# NOTE: Adjust the device path based on your instance type.
# Use `lsblk` and check model strings to identify instance store vs EBS NVMe.
CACHE_DEVICE="/dev/disk/kubernetes/nvme1"  # adjust as needed
CACHE_MOUNT="/mnt/disks/nvme-cache"

if [ -b "$CACHE_DEVICE" ]; then
    mkdir -p "$CACHE_MOUNT"
    mkfs.xfs -f "$CACHE_DEVICE"
    mount "$CACHE_DEVICE" "$CACHE_MOUNT"
    echo "$CACHE_DEVICE $CACHE_MOUNT xfs defaults,noatime 0 0" >> /etc/fstab
fi
```

### Step 2: Install Local Volume Static Provisioner

```bash
helm repo add sig-storage-local-static-provisioner \
  https://kubernetes-sigs.github.io/sig-storage-local-static-provisioner

helm install local-static-provisioner \
  sig-storage-local-static-provisioner/local-static-provisioner \
  --namespace kube-system \
  --set classes[0].name=local-nvme-sc \
  --set classes[0].hostDir=/mnt/disks \
  --set classes[0].volumeMode=Filesystem
```

### Step 3: Create StorageClass

```yaml
# storageclass-local-nvme.yaml
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: local-nvme-sc
provisioner: kubernetes.io/no-provisioner
volumeBindingMode: WaitForFirstConsumer
reclaimPolicy: Delete
```

### Step 4: Create PersistentVolume with Ephemeral Cache

```yaml
# pv-s3-ephemeral-cache.yaml
apiVersion: v1
kind: PersistentVolume
metadata:
  name: s3-training-data-pv
spec:
  capacity:
    storage: 1200Gi
  accessModes:
    - ReadOnlyMany
  mountOptions:
    - region <REGION>
    - read-only
    - metadata-ttl indefinite
  storageClassName: ""
  claimRef:
    namespace: default
    name: s3-training-data-pvc
  csi:
    driver: s3.csi.aws.com
    volumeHandle: s3-training-data-volume
    volumeAttributes:
      bucketName: <YOUR-BUCKET-NAME>

      # Ephemeral cache backed by local NVMe
      cache: ephemeral
      cacheEphemeralStorageClassName: local-nvme-sc
      cacheEphemeralStorageResourceRequest: 1000Gi
```

### Step 5: Verify udev Rules on Node (via SSM)

```bash
# Check udev rules are in place
cat /etc/udev/rules.d/90-kubernetes-discovery.rules

# Check discovery symlinks
ls -la /dev/disk/kubernetes/

# Check NVMe devices and identify instance store vs EBS
for dev in /dev/nvme*n1; do
    echo "$dev: $(cat /sys/block/$(basename $dev)/device/model 2>/dev/null)"
done

# Check dedicated cache mount
df -h | grep nvme-cache
```

---

## Auto-Recovery Behavior

| Component | Survives Node Replacement? | Why |
|-----------|---------------------------|-----|
| Mountpoint CSI driver | ✅ | Installed as EKS add-on (cluster-level) |
| kubelet NVMe symlink | ✅ | Lifecycle script re-runs on new node |
| emptyDir cache data | ❌ (cold start) | Cache is ephemeral — rebuilds on first access |
| udev rules (Option B) | ✅ | Lifecycle script re-creates them |
| NVMe format/mount (Option B) | ✅ | Lifecycle script re-formats on new node |
| Static Provisioner PVs (Option B) | ✅ | DaemonSet auto-discovers new NVMe mounts |

**Key point:** The cache data itself is always ephemeral — after a node replacement, the first read from S3 populates the cache. Subsequent reads are served from local storage. This is expected behavior and does not require manual intervention.

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

# Check Mountpoint logs
kubectl logs <mountpoint-pod-name> -n kube-system
```

---

## References

- [Mountpoint S3 CSI Driver — Caching Configuration](https://github.com/awslabs/mountpoint-s3-csi-driver/blob/main/docs/CACHING.md)
- [Mountpoint S3 CSI Driver — General Configuration](https://github.com/awslabs/mountpoint-s3-csi-driver/blob/main/docs/CONFIGURATION.md)
- [HyperPod EKS — Set up an Amazon S3 Mountpoint](https://awslabs.github.io/ai-on-sagemaker-hyperpod/docs/eks-orchestration/getting-started/Set%20up%20an%20Amazon%20S3%20mountpoint)
- [HyperPod EKS Lifecycle Script](https://github.com/awslabs/awsome-distributed-ai/blob/main/1.architectures/7.sagemaker-hyperpod-eks/LifecycleScripts/base-config/on_create_main.sh)
- [Local Volume Static Provisioner](https://github.com/kubernetes-sigs/sig-storage-local-static-provisioner)
- [Mountpoint for Amazon S3 — Open Source File Client](https://aws.amazon.com/s3/features/mountpoint/)

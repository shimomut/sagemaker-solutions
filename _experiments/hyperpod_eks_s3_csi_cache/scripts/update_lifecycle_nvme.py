#!/usr/bin/env python3
"""Automate the Option A lifecycle-script change for HyperPod EKS.

What it does:
  1. Reads the cluster's instance groups via `describe-cluster` and collects the
     LifeCycleConfig SourceS3Uri(s).
  2. Downloads the lifecycle script(s) from S3 (the file containing the
     DISK_FOR_CONTAINERD_KUBELET setting, e.g. on_create_main.sh).
  3. Replaces the `DISK_FOR_CONTAINERD_KUBELET` assignment with the requested mode:
       - auto (default): at node-creation time, prefer local instance-store NVMe
         (/opt/dlami/nvme) when it exists, otherwise fall back to the secondary
         EBS volume (/opt/sagemaker). The injected block waits (bounded) for the
         DLAMI to finish mounting NVMe before deciding, so it doesn't race the
         mount and wrongly fall back to EBS.
       - nvme: force /opt/dlami/nvme (static).
       - ebs:  force /opt/sagemaker (static / revert).
     The edit is wrapped in sentinel markers so re-runs are idempotent and can
     switch modes cleanly.
  4. Uploads the modified script back to the same S3 key (after backing up the
     original locally).
  5. Optionally replaces the affected nodes (BatchReplaceClusterNodes) so the
     updated script re-runs on fresh instances.

Node replacement is DESTRUCTIVE (instances are terminated and reprovisioned) and
is gated behind --replace-nodes plus an interactive confirmation (skip with --yes).

This script invokes the `aws` CLI via subprocess (no extra Python dependencies).

Examples:
  # Edit the LCC for auto NVMe-with-EBS-fallback (no node changes):
  python3 update_lifecycle_nvme.py --cluster-name k8-1 --target auto

  # Edit the LCC (auto) and replace the g6 node group:
  python3 update_lifecycle_nvme.py --cluster-name k8-1 --target auto \
      --replace-nodes --instance-group worker3

  # Revert to the EBS default:
  python3 update_lifecycle_nvme.py --cluster-name k8-1 --target ebs
"""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

VAR_NAME = "DISK_FOR_CONTAINERD_KUBELET"
NVME_MOUNT = "/opt/dlami/nvme"
EBS_MOUNT = "/opt/sagemaker"

# Sentinel markers wrapping the managed region, so re-runs are idempotent.
MARK_BEGIN = "# >>> hyperpod-s3-csi-cache: managed disk selection (update_lifecycle_nvme.py) >>>"
MARK_END = "# <<< hyperpod-s3-csi-cache: managed disk selection <<<"

# Matches an *active* (non-commented) assignment line, capturing leading indent.
ASSIGN_RE = re.compile(r"^(?P<indent>[ \t]*)" + VAR_NAME + r"\s*=\s*(?P<val>.*?)\s*$")
# Matches the managed region (including its trailing newline) for idempotent re-edits.
MANAGED_RE = re.compile(re.escape(MARK_BEGIN) + r".*?" + re.escape(MARK_END) + r"\n?",
                        re.DOTALL)

# Shell block injected for --target auto. Uses `echo` (not `logger`, which is
# defined later in on_create_main.sh) and is written to be `set -e`-safe.
AUTO_BODY = f'''NVME_MOUNT="{NVME_MOUNT}"
EBS_MOUNT="{EBS_MOUNT}"
# How long to wait for dlami-nvme.service to mount NVMe before falling back to EBS.
NVME_WAIT_SECONDS="${{NVME_WAIT_SECONDS:-120}}"

_has_instance_store_nvme() {{
  for _m in /sys/block/nvme*/device/model; do
    [ -e "$_m" ] || continue
    if grep -q "Amazon EC2 NVMe Instance Storage" "$_m" 2>/dev/null; then
      return 0
    fi
  done
  return 1
}}

if _has_instance_store_nvme; then
  echo "Instance-store NVMe detected; waiting up to ${{NVME_WAIT_SECONDS}}s for $NVME_MOUNT to mount..."
  _waited=0
  while ! mount | grep -q " $NVME_MOUNT "; do
    if [ "$_waited" -ge "$NVME_WAIT_SECONDS" ]; then break; fi
    sleep 5
    _waited=$((_waited + 5))
  done
  if mount | grep -q " $NVME_MOUNT "; then
    {VAR_NAME}="$NVME_MOUNT"
    echo "Selected local NVMe for containerd/kubelet: ${VAR_NAME}"
  else
    {VAR_NAME}="$EBS_MOUNT"
    echo "NVMe not mounted within ${{NVME_WAIT_SECONDS}}s; falling back to ${VAR_NAME}"
  fi
else
  {VAR_NAME}="$EBS_MOUNT"
  echo "No instance-store NVMe present; using ${VAR_NAME}"
fi
'''


def build_block(mode):
    """Return the marked managed region for the given mode (ends with a newline)."""
    if mode == "auto":
        body = AUTO_BODY
    elif mode == "nvme":
        body = f'{VAR_NAME}="{NVME_MOUNT}"\n'
    elif mode == "ebs":
        body = f'{VAR_NAME}="{EBS_MOUNT}"\n'
    else:
        raise ValueError(f"Unknown mode: {mode}")
    return f"{MARK_BEGIN}\n{body}{MARK_END}\n"


def run_aws(args, capture_json=True):
    """Run an `aws` CLI command and return parsed JSON (or raw text)."""
    cmd = ["aws"] + args
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        sys.stderr.write(f"ERROR running: {' '.join(cmd)}\n{proc.stderr}\n")
        raise SystemExit(proc.returncode)
    out = proc.stdout.strip()
    if not capture_json:
        return out
    return json.loads(out) if out else None


def parse_s3_uri(uri):
    """s3://bucket/prefix -> (bucket, prefix). Prefix may be empty."""
    if not uri.startswith("s3://"):
        raise ValueError(f"Not an S3 URI: {uri}")
    rest = uri[len("s3://"):]
    bucket, _, prefix = rest.partition("/")
    return bucket, prefix


def set_disk_config(text, mode):
    """Insert/replace the managed disk-selection region for the given mode.

    Returns (new_text, changed: bool, detail: str).
    On first run, replaces the first active assignment line with the managed
    block. On later runs, replaces the existing managed region in place.
    """
    new_block = build_block(mode)

    if MANAGED_RE.search(text):
        # Idempotent re-edit: swap the existing managed region.
        new_text = MANAGED_RE.sub(lambda m: new_block, text)
        return new_text, (new_text != text), "managed-block"

    # First run: replace the first active (non-commented) assignment line.
    lines = text.splitlines(keepends=True)
    for i, line in enumerate(lines):
        if ASSIGN_RE.match(line.rstrip("\n")):
            old_value = line.strip()
            lines[i] = new_block
            return "".join(lines), True, old_value

    raise RuntimeError(
        f"Could not find an active {VAR_NAME} assignment or managed block to edit")


def update_lcc_scripts(source_uris, mode, backup_dir, explicit_file=None):
    """Download, edit, and re-upload the lifecycle script(s). Returns count changed."""
    changed_total = 0
    os.makedirs(backup_dir, exist_ok=True)

    for uri in sorted(source_uris):
        bucket, prefix = parse_s3_uri(uri)
        list_args = ["s3api", "list-objects-v2", "--bucket", bucket,
                     "--query", "Contents[].Key", "--output", "json"]
        if prefix:
            list_args += ["--prefix", prefix]
        keys = run_aws(list_args) or []

        # Limit to shell scripts; optionally a single explicit file.
        candidates = [k for k in keys if k.endswith(".sh")]
        if explicit_file:
            candidates = [k for k in candidates if k.endswith(explicit_file)]

        for key in candidates:
            with tempfile.TemporaryDirectory() as tmp:
                local = os.path.join(tmp, os.path.basename(key))
                run_aws(["s3", "cp", f"s3://{bucket}/{key}", local,
                         "--only-show-errors"], capture_json=False)
                with open(local, "r", encoding="utf-8") as fh:
                    text = fh.read()

                if VAR_NAME not in text:
                    continue

                new_text, changed, detail = set_disk_config(text, mode)
                print(f"  {bucket}/{key}: {detail}")
                if not changed:
                    print(f"    -> already in mode {mode!r} (no change)")
                    continue

                # Back up the original before overwriting.
                backup_path = os.path.join(backup_dir, key.replace("/", "_"))
                with open(backup_path, "w", encoding="utf-8") as fh:
                    fh.write(text)

                with open(local, "w", encoding="utf-8") as fh:
                    fh.write(new_text)
                run_aws(["s3", "cp", local, f"s3://{bucket}/{key}",
                         "--only-show-errors"], capture_json=False)
                print(f"    -> set mode {mode!r} (backup: {backup_path})")
                changed_total += 1

    return changed_total


def list_node_ids(cluster, region, groups):
    """Return instance IDs, optionally filtered to the given instance groups."""
    summaries = run_aws(["sagemaker", "list-cluster-nodes",
                         "--cluster-name", cluster, "--region", region,
                         "--query", "ClusterNodeSummaries[]",
                         "--output", "json"]) or []
    nodes = []
    for s in summaries:
        grp = s.get("InstanceGroupName")
        if groups and grp not in groups:
            continue
        nodes.append((s.get("InstanceId"), grp, s.get("InstanceType")))
    return nodes


def replace_nodes(cluster, region, nodes, assume_yes):
    """Call BatchReplaceClusterNodes for the given nodes (destructive)."""
    if not nodes:
        print("No matching nodes to replace.")
        return
    print("\nThe following nodes will be REPLACED (terminated + reprovisioned):")
    for nid, grp, itype in nodes:
        print(f"  - {nid}  ({grp}, {itype})")
    print("This is disruptive: running workloads on these nodes will be killed,\n"
          "and the new instances will re-run the updated lifecycle script.")

    if not assume_yes:
        reply = input("Proceed with replacement? Type 'yes' to continue: ").strip()
        if reply != "yes":
            print("Aborted; no nodes were replaced.")
            return

    node_ids = [nid for nid, _, _ in nodes]
    result = run_aws(["sagemaker", "batch-replace-cluster-nodes",
                      "--cluster-name", cluster, "--region", region,
                      "--node-ids", *node_ids, "--output", "json"])
    print("BatchReplaceClusterNodes response:")
    print(json.dumps(result, indent=2))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cluster-name", required=True,
                    help="HyperPod cluster name (e.g. k8-1)")
    ap.add_argument("--region", default=os.environ.get("AWS_REGION", "us-west-2"))
    ap.add_argument("--target", choices=["auto", "nvme", "ebs"], default="auto",
                    help="auto=prefer NVMe, fall back to EBS at runtime (default); "
                         "nvme=force /opt/dlami/nvme; ebs=force /opt/sagemaker (revert)")
    ap.add_argument("--lcc-file",
                    help="Only edit the LCC file with this basename "
                         "(default: auto-detect any .sh containing the variable)")
    ap.add_argument("--backup-dir", default=".lcc-backup",
                    help="Local directory for original-script backups")
    ap.add_argument("--replace-nodes", action="store_true",
                    help="After editing, replace nodes so the script re-runs")
    ap.add_argument("--instance-group", action="append", default=[],
                    help="Restrict node replacement to this instance group "
                         "(repeatable). Required with --replace-nodes.")
    ap.add_argument("--yes", action="store_true",
                    help="Skip the interactive confirmation for node replacement")
    args = ap.parse_args()

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_dir = os.path.join(args.backup_dir, stamp)

    print(f"Cluster: {args.cluster_name} ({args.region})")
    print(f"Mode   : {args.target}\n")

    groups = run_aws(["sagemaker", "describe-cluster",
                      "--cluster-name", args.cluster_name, "--region", args.region,
                      "--query", "InstanceGroups[]", "--output", "json"]) or []
    source_uris = {g["LifeCycleConfig"]["SourceS3Uri"] for g in groups
                   if g.get("LifeCycleConfig", {}).get("SourceS3Uri")}
    if not source_uris:
        print("No LifeCycleConfig SourceS3Uri found on any instance group.")
        raise SystemExit(1)

    print("Updating lifecycle script(s) in S3:")
    changed = update_lcc_scripts(source_uris, args.target, backup_dir, args.lcc_file)
    if changed == 0:
        print("\nNo lifecycle files changed.")
    else:
        print(f"\nUpdated {changed} lifecycle file(s).")

    if not args.replace_nodes:
        print("\nDone. Node replacement was NOT requested.")
        print("New/replaced nodes will pick up the change; existing nodes keep the "
              "old layout until replaced.")
        return

    if not args.instance_group:
        print("\n--replace-nodes requires at least one --instance-group "
              "(refusing to replace ALL nodes implicitly).")
        raise SystemExit(2)

    nodes = list_node_ids(args.cluster_name, args.region, args.instance_group)
    replace_nodes(args.cluster_name, args.region, nodes, args.yes)


if __name__ == "__main__":
    main()

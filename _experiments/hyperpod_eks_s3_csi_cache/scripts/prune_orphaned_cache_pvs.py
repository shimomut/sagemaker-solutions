#!/usr/bin/env python3
"""Detect (and optionally delete) orphaned local-cache PersistentVolumes.

Option B's Local Volume Static Provisioner creates node-pinned PVs. When a node
is replaced or removed, its never-bound (`Available`) PVs are left behind with
node-affinity to a node that no longer exists. This tool finds those orphans and
can delete them.

A PV is considered orphaned when ALL of the following hold:
  - storageClassName matches --storage-class (default: nvme-cache)
  - status.phase == Available  (never deletes Bound/Released PVs)
  - its node-affinity hostname refers to a node not currently in the cluster

By default it only lists orphans (dry run). Pass --delete to remove them.

Uses the `kubectl` CLI via subprocess (no extra Python dependencies).

Examples:
  python3 prune_orphaned_cache_pvs.py                  # list orphans (dry run)
  python3 prune_orphaned_cache_pvs.py --delete         # delete orphans
  python3 prune_orphaned_cache_pvs.py --storage-class nvme-cache --delete
"""

import argparse
import json
import subprocess
import sys


def kubectl_json(args):
    proc = subprocess.run(["kubectl"] + args, capture_output=True, text=True)
    if proc.returncode != 0:
        sys.stderr.write(f"ERROR: kubectl {' '.join(args)}\n{proc.stderr}\n")
        raise SystemExit(proc.returncode)
    return json.loads(proc.stdout) if proc.stdout.strip() else {}


def affinity_hostnames(pv):
    """Extract the kubernetes.io/hostname values from a PV's node affinity."""
    names = set()
    terms = (pv.get("spec", {}).get("nodeAffinity", {})
             .get("required", {}).get("nodeSelectorTerms", []))
    for term in terms:
        for expr in term.get("matchExpressions", []):
            if expr.get("key") == "kubernetes.io/hostname":
                names.update(expr.get("values", []))
    return names


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--storage-class", default="nvme-cache",
                    help="Only consider PVs in this StorageClass (default: nvme-cache)")
    ap.add_argument("--delete", action="store_true",
                    help="Delete the orphaned PVs (default: list only / dry run)")
    args = ap.parse_args()

    existing_nodes = {n["metadata"]["name"]
                      for n in kubectl_json(["get", "nodes", "-o", "json"]).get("items", [])}

    orphans = []
    for pv in kubectl_json(["get", "pv", "-o", "json"]).get("items", []):
        spec = pv.get("spec", {})
        if spec.get("storageClassName") != args.storage_class:
            continue
        if pv.get("status", {}).get("phase") != "Available":
            continue
        hostnames = affinity_hostnames(pv)
        # Orphaned only if it is pinned to node(s), none of which still exist.
        if hostnames and not (hostnames & existing_nodes):
            orphans.append((pv["metadata"]["name"], sorted(hostnames)))

    if not orphans:
        print(f"No orphaned '{args.storage_class}' PVs found.")
        return

    print(f"Orphaned '{args.storage_class}' PVs (Available, node no longer exists):")
    for name, hosts in orphans:
        print(f"  - {name}  (pinned to: {', '.join(hosts)})")

    if not args.delete:
        print(f"\n{len(orphans)} orphan(s). Re-run with --delete to remove them.")
        return

    print()
    for name, _ in orphans:
        proc = subprocess.run(["kubectl", "delete", "pv", name],
                              capture_output=True, text=True)
        sys.stdout.write(proc.stdout)
        if proc.returncode != 0:
            sys.stderr.write(proc.stderr)
    print(f"\nDeleted {len(orphans)} orphaned PV(s).")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Prepare the single-template HyperPod x DevOps Agent deployment.

Two subcommands, both driven by the Makefile, that turn the source tree into
inputs 'aws cloudformation deploy' can consume:

  embed    Inline each deploy/lambda/*.py into hyperpod_devops_agent.yaml at its
           "# <NAME>_CODE_PLACEHOLDER" marker, producing
           hyperpod_devops_agent.embedded.yaml. This mirrors the repo's existing
           awk-based embed convention, but handles the five distinct placeholders
           in one pass.

  sync-skills
           For each skill directory under ../skills/, stage its contents
           (bundling docs/hyperpod-mental-model.md into references/ when the
           SKILL.md references it — the same logic scripts/07_upload_skill.sh
           used), zip it, upload to s3://<bucket>/skills/<name>.zip, and print
           a JSON object with the manifest + a content-hash version:
               {"manifest": [...], "version": "<sha256>"}
           The Makefile captures that and passes it to CloudFormation.

Kept dependency-free (stdlib only) so it runs in the solution venv or bare.
"""
import argparse
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile


HERE = os.path.dirname(os.path.abspath(__file__))
SOLUTION_ROOT = os.path.dirname(HERE)              # _experiments/hyperpod_devops_agent
REPO_ROOT = os.path.dirname(os.path.dirname(SOLUTION_ROOT))  # sagemaker-solutions
MENTAL_MODEL = os.path.join(REPO_ROOT, "docs", "hyperpod-mental-model.md")

LAMBDA_DIR = os.path.join(HERE, "lambda")
SKILLS_DIR = os.path.join(SOLUTION_ROOT, "skills")

# placeholder marker -> lambda source file. These are inlined into the template
# as ZipFile code. The skill uploader is NOT here: its Asset API is newer than
# the Lambda runtime's bundled boto3, so it ships as an S3 zip with a current
# boto3 bundled (see build_skill_uploader).
PLACEHOLDERS = {
    "WEBHOOK_BRIDGE_CODE_PLACEHOLDER": "webhook_bridge.py",
    "PERIODIC_AUDIT_CODE_PLACEHOLDER": "periodic_audit.py",
    "EMAIL_NOTIFIER_CODE_PLACEHOLDER": "email_notifier.py",
    "CR_WEBHOOK_PROVISIONER_CODE_PLACEHOLDER": "cr_webhook_provisioner.py",
}

# Minimum boto3 that includes the DevOps Agent Asset API (list_assets etc.).
BOTO3_MIN = "boto3>=1.40.0"


def _indent_of(line: str) -> str:
    return line[: len(line) - len(line.lstrip(" "))]


def embed(template_in: str, template_out: str) -> None:
    with open(template_in) as f:
        lines = f.readlines()

    out: list[str] = []
    for line in lines:
        stripped = line.strip()
        marker = stripped.lstrip("# ").strip()
        if stripped.startswith("#") and marker in PLACEHOLDERS:
            indent = _indent_of(line)
            src_path = os.path.join(LAMBDA_DIR, PLACEHOLDERS[marker])
            with open(src_path) as sf:
                for code_line in sf.read().splitlines():
                    out.append((indent + code_line).rstrip() + "\n" if code_line else "\n")
        else:
            out.append(line)

    with open(template_out, "w") as f:
        f.writelines(out)
    print(f"embedded {len(PLACEHOLDERS)} Lambda sources -> {template_out}")


def _parse_skill_frontmatter(skill_md: str) -> tuple[str, list[str]]:
    text = open(skill_md).read()
    m = re.search(r"^---\s*\n(.*?)\n---", text, re.S)
    if not m:
        sys.exit(f"{skill_md}: missing frontmatter")
    fm = m.group(1)
    name_match = re.search(r"^name:\s*(\S+)", fm, re.M)
    if not name_match:
        sys.exit(f"{skill_md}: frontmatter missing 'name:'")
    name = name_match.group(1).strip()
    at_match = re.search(r"agent_types:\s*\[([^\]]*)\]", fm)
    if at_match:
        agent_types = [
            t.strip().strip('"').strip("'")
            for t in at_match.group(1).split(",")
            if t.strip()
        ]
    else:
        agent_types = ["GENERIC"]
    return name, agent_types


def _build_skill_zip(skill_path: str, skill_md: str) -> bytes:
    """Zip a skill dir deterministically; bundle the mental-model doc if referenced.

    Fixed member timestamps + sorted order so identical content always yields
    identical bytes — the content hash only changes when a skill actually changes.
    """
    references_needed = "hyperpod-mental-model.md" in open(skill_md).read()

    members: list[tuple[str, str]] = []  # (arcname, abs_path)
    for root, dirs, files in os.walk(skill_path):
        dirs[:] = sorted(d for d in dirs if d != "__pycache__")
        for fn in sorted(files):
            if fn == ".DS_Store":
                continue
            abs_path = os.path.join(root, fn)
            members.append((os.path.relpath(abs_path, skill_path), abs_path))
    if references_needed:
        if not os.path.exists(MENTAL_MODEL):
            sys.exit(
                f"SKILL.md references hyperpod-mental-model.md but "
                f"{MENTAL_MODEL} not found"
            )
        members.append(("references/hyperpod-mental-model.md", MENTAL_MODEL))
    members.sort()

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for arcname, abs_path in members:
            info = zipfile.ZipInfo(arcname, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            with open(abs_path, "rb") as fp:
                zf.writestr(info, fp.read())
    return buf.getvalue()


def sync_skills(bucket: str, region: str) -> None:
    if not os.path.isdir(SKILLS_DIR):
        sys.exit(f"skills dir not found: {SKILLS_DIR}")

    manifest: list[dict] = []
    hasher = hashlib.sha256()
    for entry in sorted(os.listdir(SKILLS_DIR)):
        skill_path = os.path.join(SKILLS_DIR, entry)
        skill_md = os.path.join(skill_path, "SKILL.md")
        if not os.path.isdir(skill_path) or not os.path.isfile(skill_md):
            continue  # skip 'upstream/' clone and non-skill dirs
        name, agent_types = _parse_skill_frontmatter(skill_md)
        blob = _build_skill_zip(skill_path, skill_md)
        key = f"skills/{name}.zip"
        # Deterministic hash: name + agent_types + zip bytes.
        hasher.update(name.encode())
        hasher.update(json.dumps(agent_types, sort_keys=True).encode())
        hasher.update(blob)
        with tempfile.NamedTemporaryFile(suffix=".zip") as tmp:
            tmp.write(blob)
            tmp.flush()
            subprocess.run(
                ["aws", "s3api", "put-object",
                 "--bucket", bucket, "--key", key,
                 "--body", tmp.name, "--region", region],
                check=True,
                stdout=subprocess.DEVNULL,
            )
        print(f"uploaded s3://{bucket}/{key} ({len(blob)} bytes)", file=sys.stderr)
        manifest.append({"name": name, "zipKey": key, "agentTypes": agent_types})

    if not manifest:
        sys.exit(f"no skills found under {SKILLS_DIR}")

    print(json.dumps({"manifest": manifest, "version": hasher.hexdigest()[:32]}))


def build_skill_uploader(bucket: str, region: str) -> None:
    """Package the skill uploader Lambda (handler + cfnresponse + current boto3)
    as an S3 zip and upload it. The Lambda runtime's bundled boto3 predates the
    DevOps Agent Asset API (list_assets etc.), so we bundle a current one.

    Prints {"bucket": ..., "key": ...} for the template's Code.S3Bucket/S3Key.
    """
    stage = tempfile.mkdtemp(prefix="skilluploader-")
    try:
        # index.py = handler; cfnresponse.py = the S3-package shim.
        with open(os.path.join(LAMBDA_DIR, "cr_skill_uploader.py")) as f:
            src = f.read()
        with open(os.path.join(stage, "index.py"), "w") as f:
            f.write(src)
        with open(os.path.join(LAMBDA_DIR, "cfnresponse.py")) as f:
            shim = f.read()
        with open(os.path.join(stage, "cfnresponse.py"), "w") as f:
            f.write(shim)

        print(f"pip installing {BOTO3_MIN} into the package...", file=sys.stderr)
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "--quiet",
             "--target", stage, BOTO3_MIN],
            check=True,
        )

        # Deterministic-ish zip (member order sorted; fixed timestamps).
        members: list[tuple[str, str]] = []
        for root, dirs, files in os.walk(stage):
            dirs[:] = sorted(d for d in dirs if d != "__pycache__")
            for fn in sorted(files):
                if fn.endswith(".pyc") or fn == ".DS_Store":
                    continue
                abs_path = os.path.join(root, fn)
                members.append((os.path.relpath(abs_path, stage), abs_path))
        members.sort()

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for arcname, abs_path in members:
                info = zipfile.ZipInfo(arcname, date_time=(1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o644 << 16
                with open(abs_path, "rb") as fp:
                    zf.writestr(info, fp.read())
        blob = buf.getvalue()

        key = "lambda/skill_uploader.zip"
        with tempfile.NamedTemporaryFile(suffix=".zip") as tmp:
            tmp.write(blob)
            tmp.flush()
            subprocess.run(
                ["aws", "s3api", "put-object",
                 "--bucket", bucket, "--key", key,
                 "--body", tmp.name, "--region", region],
                check=True,
                stdout=subprocess.DEVNULL,
            )
        print(f"uploaded s3://{bucket}/{key} ({len(blob)} bytes)", file=sys.stderr)
        print(json.dumps({"bucket": bucket, "key": key}))
    finally:
        shutil.rmtree(stage, ignore_errors=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    e = sub.add_parser("embed")
    e.add_argument("--in", dest="template_in", required=True)
    e.add_argument("--out", dest="template_out", required=True)

    s = sub.add_parser("sync-skills")
    s.add_argument("--bucket", required=True)
    s.add_argument("--region", required=True)

    b = sub.add_parser("build-skill-uploader")
    b.add_argument("--bucket", required=True)
    b.add_argument("--region", required=True)

    args = ap.parse_args()
    if args.cmd == "embed":
        embed(args.template_in, args.template_out)
    elif args.cmd == "sync-skills":
        sync_skills(args.bucket, args.region)
    elif args.cmd == "build-skill-uploader":
        build_skill_uploader(args.bucket, args.region)


if __name__ == "__main__":
    main()

# Repository Guide for Claude

This repository follows the conventions documented in [Kiro steering documents](.kiro/steering/). Read these before making changes:

- [.kiro/steering/product.md](.kiro/steering/product.md) — what this repo is for and the major component groups (HyperPod, Training, Inference, shared infra).
- [.kiro/steering/structure.md](.kiro/steering/structure.md) — directory layout, naming conventions (`hyperpod_*`, `training_*`, `inference_*`, `sagemaker_*`), and the standard files inside each solution directory.
- [.kiro/steering/tech.md](.kiro/steering/tech.md) — tech stack, common Makefile targets, and **script conventions** (see below).
- [.kiro/steering/confidentiality.md](.kiro/steering/confidentiality.md) — no customer names or identifying scenarios anywhere in the repo.

## Key script conventions (from tech.md)

- **Use a Python virtual environment (venv) or container** when installing additional packages — never modify the system Python environment.
- Do NOT `chmod +x` scripts; keep them at default `644`.
- Always invoke scripts through their interpreter explicitly: `bash script.sh`, `python3 script.py`. Makefiles and docs follow the same rule.

## Running solution scripts

Each solution lives in its own top-level directory with a `requirements.txt`. Typical setup:

```bash
cd <solution_dir>
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 <main_script>.py ...
```

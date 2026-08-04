# Repository Guide for Claude

This repository follows the conventions documented in [Kiro steering documents](.kiro/steering/). Read these before making changes:

- [.kiro/steering/product.md](.kiro/steering/product.md) — what this repo is for and the major component groups (HyperPod, Training, Inference, shared infra).
- [.kiro/steering/structure.md](.kiro/steering/structure.md) — directory layout, naming conventions (`hyperpod_*`, `training_*`, `inference_*`, `sagemaker_*`), and the standard files inside each solution directory.
- [.kiro/steering/tech.md](.kiro/steering/tech.md) — tech stack, common Makefile targets, and **script conventions** (see below).
- [.kiro/steering/confidentiality.md](.kiro/steering/confidentiality.md) — no customer names or identifying scenarios anywhere in the repo.

## Technical knowledge base (read this when working on HyperPod behavior)

The curated HyperPod mental model lives in [docs/](docs/):

- [docs/hyperpod-mental-model.md](docs/hyperpod-mental-model.md) — the main curated doc. Read it before answering questions about how HyperPod behaves; don't rely on training-data assumptions ("basically EC2 + Slurm/EKS" is the trap).
- [docs/mental-model/](docs/mental-model/) — dedicated supplemental docs for large topics, linked from the main doc.
- [docs/knowledge-updates/](docs/knowledge-updates/) — staging inbox for new findings, plus the maintenance process.

**When you learn something new about HyperPod during a session**, do NOT edit the main doc mid-discovery. Append a classified finding to a dated file `docs/knowledge-updates/hyperpod-new-knowledge-<YYYY-MM-DD>.md` (copy `docs/knowledge-updates/TEMPLATE.md` if today's file doesn't exist). **When asked to curate / "brush up the docs"**, run the merge → archive → log process defined in [docs/README.md](docs/README.md).

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

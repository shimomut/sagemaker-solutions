#!/usr/bin/env bash
# Clone (or pull) awslabs/agent-plugins, strip every hyperpod-* skill's
# scripts/ directory (DevOps Agent skills are "non-executable documents only"),
# then upload each skill to the configured Agent Space.
#
# Re-runnable: subsequent runs `git pull` instead of re-cloning, and
# update-asset is used when the skill name already exists in the Agent Space.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${HERE}/.." && pwd)"
source "${HERE}/config.sh"

: "${UPSTREAM_REPO_URL:=https://github.com/awslabs/agent-plugins.git}"
: "${UPSTREAM_DIR:=${ROOT}/skills/upstream}"
: "${UPSTREAM_REF:=main}"
UPSTREAM_SKILLS_DIR="${UPSTREAM_DIR}/plugins/sagemaker-ai/skills"

# Curated default — only the upstream skills whose in-guardrail (API + kubectl)
# portion is useful inside DevOps Agent. Skills whose entire procedure depends
# on SSM (issue-report, version-checker, ssm itself) are excluded by default
# because the guardrail blocks ssm:StartSession — loading them would confuse the
# agent with unreachable instructions. slurm-debugger is excluded because its
# diagnostic recipes require SSM to the controller. See the README's "Impact on
# the imported skills" section.
#
# Override with SKILLS='name1 name2' to import a different set.
DEFAULT_SKILLS=(
    hyperpod-cluster-debugger
    hyperpod-nccl
    hyperpod-node-debugger
    hyperpod-performance-debugger
)

# Skills that exist upstream but are intentionally excluded from the default
# import. Kept as a comment so re-additions are deliberate.
#   hyperpod-issue-report      - whole skill is on-node collection
#   hyperpod-slurm-debugger    - controller-side SSM
#   hyperpod-ssm               - SSM driver itself
#   hyperpod-version-checker   - whole skill is on-node reads

if [[ -n "${SKILLS:-}" ]]; then
    read -r -a SKILLS_TO_IMPORT <<< "${SKILLS}"
else
    SKILLS_TO_IMPORT=("${DEFAULT_SKILLS[@]}")
fi

if [[ ! -f "${STATE_FILE}" ]]; then
    echo "Error: ${STATE_FILE} not found. Run 'make setup' first." >&2
    exit 1
fi

AGENT_SPACE_ID="$(python3 -c "import json,sys; print(json.load(open(sys.argv[1])).get('agentSpaceId',''))" "${STATE_FILE}")"
if [[ -z "${AGENT_SPACE_ID}" ]]; then
    echo "Error: agentSpaceId missing from ${STATE_FILE}." >&2
    exit 1
fi

echo "==> Configuration"
print_config
echo "Agent Space ID:   ${AGENT_SPACE_ID}"
echo "Upstream repo:    ${UPSTREAM_REPO_URL} (${UPSTREAM_REF})"
echo "Upstream dir:     ${UPSTREAM_DIR}"
echo "Skills to import: ${SKILLS_TO_IMPORT[*]}"
echo

# ---- Step 1: clone or pull upstream ---------------------------------------
if [[ -d "${UPSTREAM_DIR}/.git" ]]; then
    echo "==> Pulling latest upstream"
    git -C "${UPSTREAM_DIR}" fetch --depth 1 origin "${UPSTREAM_REF}"
    git -C "${UPSTREAM_DIR}" reset --hard "origin/${UPSTREAM_REF}"
else
    echo "==> Cloning upstream"
    rm -rf "${UPSTREAM_DIR}"
    git clone --depth 1 --branch "${UPSTREAM_REF}" "${UPSTREAM_REPO_URL}" "${UPSTREAM_DIR}"
fi
echo "    upstream HEAD: $(git -C "${UPSTREAM_DIR}" rev-parse --short HEAD)"
echo

# ---- Step 2: process each skill -------------------------------------------
WORK_DIR="$(mktemp -d)"
trap 'rm -rf "${WORK_DIR}"' EXIT

import_one_skill() {
    local skill_name="$1"
    local src="${UPSTREAM_SKILLS_DIR}/${skill_name}"
    if [[ ! -d "${src}" ]]; then
        echo "    SKIP ${skill_name}: source directory not found at ${src}"
        return
    fi

    # Copy to working dir and strip scripts/ (DevOps Agent skills are non-executable).
    local staged="${WORK_DIR}/${skill_name}"
    rm -rf "${staged}"
    cp -R "${src}" "${staged}"
    if [[ -d "${staged}/scripts" ]]; then
        echo "    stripping scripts/ from ${skill_name}"
        rm -rf "${staged}/scripts"
    fi

    # Confirm SKILL.md exists.
    if [[ ! -f "${staged}/SKILL.md" ]]; then
        echo "    SKIP ${skill_name}: SKILL.md missing after staging" >&2
        return
    fi

    # Hand off to the existing upload script. SKILL_DIR honors absolute paths.
    echo "    uploading ${skill_name}"
    SKILL_DIR="${staged}" bash "${HERE}/07_upload_skill.sh"
}

for skill in "${SKILLS_TO_IMPORT[@]}"; do
    echo
    echo "==> Importing ${skill}"
    import_one_skill "${skill}"
done

echo
echo "Done. List with 'make list-skills'."

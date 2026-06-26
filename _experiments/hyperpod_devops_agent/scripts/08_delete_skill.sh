#!/usr/bin/env bash
# Deletes a skill from the configured Agent Space.
# Provide either SKILL_NAME=... directly, or SKILL_DIR=... to read the name
# from the directory's SKILL.md frontmatter.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${HERE}/.." && pwd)"
source "${HERE}/config.sh"

if [[ ! -f "${STATE_FILE}" ]]; then
    echo "Error: ${STATE_FILE} not found." >&2
    exit 1
fi

AGENT_SPACE_ID="$(python3 -c "import json,sys; print(json.load(open(sys.argv[1])).get('agentSpaceId',''))" "${STATE_FILE}")"
if [[ -z "${AGENT_SPACE_ID}" ]]; then
    echo "Error: agentSpaceId missing from ${STATE_FILE}." >&2
    exit 1
fi

if [[ -n "${SKILL_NAME:-}" ]]; then
    NAME="${SKILL_NAME}"
elif [[ -n "${SKILL_DIR:-}" ]]; then
    if [[ "${SKILL_DIR}" == /* ]]; then
        SKILL_PATH="${SKILL_DIR}"
    else
        SKILL_PATH="${ROOT}/${SKILL_DIR}"
    fi
    NAME="$(python3 - "${SKILL_PATH}/SKILL.md" <<'PY'
import sys, re
text = open(sys.argv[1]).read()
m = re.search(r"^---\s*\n(.*?)\n---", text, re.S)
if not m:
    sys.exit("SKILL.md is missing frontmatter")
m = re.search(r"^name:\s*(\S+)", m.group(1), re.M)
if not m:
    sys.exit("SKILL.md frontmatter missing 'name:'")
print(m.group(1).strip())
PY
)"
else
    echo "Error: provide SKILL_NAME=... or SKILL_DIR=..." >&2
    exit 1
fi

echo "==> Looking up skill '${NAME}' in Agent Space ${AGENT_SPACE_ID}"
ASSET_ID="$(aws devops-agent list-assets \
    --region "${REGION}" \
    --agent-space-id "${AGENT_SPACE_ID}" \
    --max-results 100 \
    --query "items[?metadata.name=='${NAME}' && assetType=='skill'].assetId | [0]" \
    --output text 2>/dev/null || true)"

if [[ -z "${ASSET_ID}" || "${ASSET_ID}" == "None" ]]; then
    echo "    no skill named '${NAME}' found"
    exit 0
fi

echo "    found ${ASSET_ID}, deleting"
aws devops-agent delete-asset \
    --region "${REGION}" \
    --agent-space-id "${AGENT_SPACE_ID}" \
    --asset-id "${ASSET_ID}"

echo "Done."

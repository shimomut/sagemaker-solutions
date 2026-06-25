#!/usr/bin/env bash
# Deletes a skill from the configured Agent Space, matched by SKILL.md name.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${HERE}/.." && pwd)"
source "${HERE}/config.sh"

: "${SKILL_DIR:=skills/hyperpod-investigation}"
SKILL_PATH="${ROOT}/${SKILL_DIR}"

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
else
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

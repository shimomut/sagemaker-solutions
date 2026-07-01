#!/usr/bin/env bash
# Zips a Skill directory (SKILL.md + optional references/, assets/) and uploads
# it to the configured Agent Space via the Asset API. Re-runnable: if a skill
# with the same name already exists in the Agent Space, update-asset is called
# instead of create-asset, preserving the existing asset id.
#
# Usage:
#     SKILL_DIR=skills/my-skill make upload-skill
#     SKILL_DIR=/abs/path make upload-skill          # absolute paths accepted
#
# The skill name comes from the SKILL.md frontmatter and must match the
# `name:` field there. The script greps it out of the file.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${HERE}/.." && pwd)"
source "${HERE}/config.sh"

if [[ -z "${SKILL_DIR:-}" ]]; then
    echo "Error: SKILL_DIR is required (e.g. SKILL_DIR=skills/my-skill make upload-skill)" >&2
    exit 1
fi
# If SKILL_DIR is an absolute path, use it as-is. Otherwise resolve it
# relative to the project root.
if [[ "${SKILL_DIR}" == /* ]]; then
    SKILL_PATH="${SKILL_DIR}"
else
    SKILL_PATH="${ROOT}/${SKILL_DIR}"
fi

if [[ ! -d "${SKILL_PATH}" ]]; then
    echo "Error: skill directory not found: ${SKILL_PATH}" >&2
    exit 1
fi
if [[ ! -f "${SKILL_PATH}/SKILL.md" ]]; then
    echo "Error: ${SKILL_PATH}/SKILL.md is missing" >&2
    exit 1
fi
if [[ ! -f "${STATE_FILE}" ]]; then
    echo "Error: ${STATE_FILE} not found. Run 'make setup' first." >&2
    exit 1
fi

AGENT_SPACE_ID="$(python3 -c "import json,sys; print(json.load(open(sys.argv[1])).get('agentSpaceId',''))" "${STATE_FILE}")"
if [[ -z "${AGENT_SPACE_ID}" ]]; then
    echo "Error: agentSpaceId missing from ${STATE_FILE}. Run 'make agent-space' first." >&2
    exit 1
fi

# Extract the skill name + agent_types from the SKILL.md frontmatter.
read -r SKILL_NAME SKILL_AGENT_TYPES <<<"$(python3 - "${SKILL_PATH}/SKILL.md" <<'PY'
import sys, re, json
text = open(sys.argv[1]).read()
m = re.search(r"^---\s*\n(.*?)\n---", text, re.S)
if not m:
    sys.exit("SKILL.md is missing frontmatter")
fm = m.group(1)
name_match = re.search(r"^name:\s*(\S+)", fm, re.M)
if not name_match:
    sys.exit("SKILL.md frontmatter is missing 'name:'")
name = name_match.group(1).strip()
# agent_types may live at the top level or under metadata: in either YAML form.
# Accept inline list (agent_types: ["A", "B"]) — simple parse, no full YAML lib.
agent_types_match = re.search(r"agent_types:\s*\[([^\]]*)\]", fm)
if agent_types_match:
    tokens = [t.strip().strip('"').strip("'") for t in agent_types_match.group(1).split(",")]
    agent_types = [t for t in tokens if t]
else:
    agent_types = ["GENERIC"]
print(name, json.dumps(agent_types))
PY
)"

echo "==> Configuration"
print_config
echo "Agent Space ID: ${AGENT_SPACE_ID}"
echo "Skill dir:      ${SKILL_PATH}"
echo "Skill name:     ${SKILL_NAME}"
echo "Agent types:    ${SKILL_AGENT_TYPES}"
echo

# Stage the skill contents into a temp directory before zipping. This lets us
# bundle shared references (like the canonical HyperPod mental-model doc)
# that live outside the skill directory, without polluting the source-controlled
# skill directory. The repo's docs/hyperpod-mental-model.md remains the single
# source of truth; a fresh copy is dropped into <staging>/references/ when the
# skill's SKILL.md references it.
STAGE_DIR="$(mktemp -d)"
ZIP_DIR="$(mktemp -d)"
ZIP_PATH="${ZIP_DIR}/${SKILL_NAME}.zip"
INPUT_JSON_PATH="$(mktemp).json"
trap 'rm -rf "${STAGE_DIR}" "${ZIP_DIR}"; rm -f "${INPUT_JSON_PATH}"' EXIT

echo "==> Staging skill to ${STAGE_DIR}"
( cd "${SKILL_PATH}" && tar -cf - --exclude='.DS_Store' --exclude='__pycache__' . ) \
    | ( cd "${STAGE_DIR}" && tar -xf - )

REPO_MENTAL_MODEL="$(cd "${ROOT}/../.." && pwd)/docs/hyperpod-mental-model.md"
if grep -q 'hyperpod-mental-model\.md' "${SKILL_PATH}/SKILL.md"; then
    if [[ ! -f "${REPO_MENTAL_MODEL}" ]]; then
        echo "Error: SKILL.md references hyperpod-mental-model.md but source doc not found at ${REPO_MENTAL_MODEL}" >&2
        exit 1
    fi
    echo "==> Bundling references/hyperpod-mental-model.md (fresh copy from ${REPO_MENTAL_MODEL})"
    mkdir -p "${STAGE_DIR}/references"
    cp "${REPO_MENTAL_MODEL}" "${STAGE_DIR}/references/hyperpod-mental-model.md"
fi

echo "==> Zipping skill -> ${ZIP_PATH}"
( cd "${STAGE_DIR}" && zip -r -q "${ZIP_PATH}" . -x '*.DS_Store' '*/__pycache__/*' )
echo "    zip size: $(wc -c < "${ZIP_PATH}") bytes"

# Look up an existing asset by name.
echo
echo "==> Checking for existing skill asset named '${SKILL_NAME}'"
EXISTING_ID="$(aws devops-agent list-assets \
    --region "${REGION}" \
    --agent-space-id "${AGENT_SPACE_ID}" \
    --max-results 100 \
    --query "items[?metadata.name=='${SKILL_NAME}' && assetType=='skill'].assetId | [0]" \
    --output text 2>/dev/null || true)"

CONTENT_JSON="$(python3 - "${ZIP_PATH}" <<'PY'
import base64, json, sys
with open(sys.argv[1], "rb") as f:
    blob = f.read()
print(json.dumps({"zip": {"zipFile": base64.b64encode(blob).decode("ascii")}}))
PY
)"

# The --content blob argument needs the bytes; passing as fileb:// avoids
# stuffing the whole zip onto the command line. Use cli-input-json instead for
# clean blob handling. INPUT_JSON_PATH is cleaned up by the EXIT trap set above.

if [[ -n "${EXISTING_ID}" && "${EXISTING_ID}" != "None" ]]; then
    echo "    updating existing asset ${EXISTING_ID}"
    python3 - "${INPUT_JSON_PATH}" "${AGENT_SPACE_ID}" "${EXISTING_ID}" "${ZIP_PATH}" "${SKILL_AGENT_TYPES}" <<'PY'
import base64, json, sys
out_path, agent_space_id, asset_id, zip_path, agent_types_json = sys.argv[1:]
agent_types = json.loads(agent_types_json)
with open(zip_path, "rb") as f:
    blob = f.read()
payload = {
    "agentSpaceId": agent_space_id,
    "assetId": asset_id,
    "metadata": {"agent_types": agent_types, "status": "ACTIVE"},
    "content": {"zip": {"zipFile": base64.b64encode(blob).decode("ascii")}},
}
with open(out_path, "w") as f:
    json.dump(payload, f)
PY
    aws devops-agent update-asset \
        --region "${REGION}" \
        --cli-input-json "file://${INPUT_JSON_PATH}" \
        --query 'asset.{assetId:assetId,version:version,status:metadata.status}' \
        --output table
else
    echo "    creating new asset"
    python3 - "${INPUT_JSON_PATH}" "${AGENT_SPACE_ID}" "${ZIP_PATH}" "${SKILL_AGENT_TYPES}" <<'PY'
import base64, json, sys
out_path, agent_space_id, zip_path, agent_types_json = sys.argv[1:]
agent_types = json.loads(agent_types_json)
with open(zip_path, "rb") as f:
    blob = f.read()
payload = {
    "agentSpaceId": agent_space_id,
    "assetType": "skill",
    "metadata": {"agent_types": agent_types, "status": "ACTIVE"},
    "content": {"zip": {"zipFile": base64.b64encode(blob).decode("ascii")}},
}
with open(out_path, "w") as f:
    json.dump(payload, f)
PY
    aws devops-agent create-asset \
        --region "${REGION}" \
        --cli-input-json "file://${INPUT_JSON_PATH}" \
        --query 'asset.{assetId:assetId,version:version,status:metadata.status}' \
        --output table
fi

echo
echo "==> Listing skills in Agent Space"
aws devops-agent list-assets \
    --region "${REGION}" \
    --agent-space-id "${AGENT_SPACE_ID}" \
    --max-results 50 \
    --query "items[?assetType=='skill'].{assetId:assetId,name:metadata.name,version:version,status:metadata.status,type:metadata.skill_type}" \
    --output table

echo
echo "Done."

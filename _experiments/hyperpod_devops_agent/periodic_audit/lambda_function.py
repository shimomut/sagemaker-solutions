"""Periodic-audit Lambda for the hyperpod-incident-rca skill.

Fired every N minutes by an EventBridge Scheduler rule. Synthesizes a
"periodic audit" event and POSTs it to the DevOps Agent generic webhook,
HMAC-signed the same way the webhook bridge signs real HyperPod events.

The skill receives this as a trigger with detail-type "HyperPod Periodic
Audit" and runs Phase 1 audit-mode logic — discover open fault chains in
list-cluster-events, classify, emit Resolved / Monitor / Escalate /
Suppress verdicts as appropriate. The email notifier filters Suppress
verdicts so a healthy cluster produces no email noise.

Design note — why we always invoke the skill (rather than checking
list-cluster-events from Lambda first and only invoking on open chains):

The "is anything open?" decision requires the same 7-day event-chain
analysis the skill already does. Reimplementing that logic in Lambda
would duplicate the skill and split responsibility for what counts as
"open." Letting the skill decide produces consistent verdicts at the
cost of ~96 investigations/day on a healthy cluster — well below the
concurrent quota (3) and the agent-reasoning cost on a Suppress
verdict is small (one describe-cluster + one list-cluster-events call
+ ~10s of agent reasoning).

Env vars:
  WEBHOOK_SECRET_ARN   ARN of the Secrets Manager secret holding
                       {"url": "...", "secret": "..."} (shared with bridge)
  CLUSTER_NAME         Cluster the audit covers (purely informational —
                       included in the synthetic payload metadata; the
                       skill rediscovers clusters from describe-cluster
                       on its own)
"""
import base64
import datetime
import hashlib
import hmac
import json
import os
import urllib.request
from urllib.error import HTTPError, URLError

import boto3


_secrets_cache: dict[str, str] = {}


def _load_webhook_credentials() -> tuple[str, str]:
    if "url" in _secrets_cache and "secret" in _secrets_cache:
        return _secrets_cache["url"], _secrets_cache["secret"]

    secret_arn = os.environ["WEBHOOK_SECRET_ARN"]
    client = boto3.client("secretsmanager")
    resp = client.get_secret_value(SecretId=secret_arn)
    payload = json.loads(resp["SecretString"])
    _secrets_cache["url"] = payload["url"]
    _secrets_cache["secret"] = payload["secret"]
    return _secrets_cache["url"], _secrets_cache["secret"]


def _build_payload(cluster_name: str) -> dict:
    now_iso = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.000Z")
    now_compact = datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    incident_id = f"hyperpod-audit-{now_compact}"
    return {
        "eventType": "incident",
        "incidentId": incident_id,
        "action": "created",
        "priority": "LOW",
        # Stable audit-event title so DevOps Agent's automatic task
        # deduplication (~30 minute window) reliably absorbs back-to-back
        # audits — that's free idle-cluster cost reduction. When the platform
        # dedup window expires and a fresh audit DOES run the skill, the
        # skill's rule-3 (stale-evidence Suppress) provides the second
        # protection layer based on signature-set comparison.
        "title": f"HyperPod periodic audit: {cluster_name}",
        "description": (
            f"Periodic audit invocation for HyperPod cluster '{cluster_name}'. "
            f"No specific incident is referenced. The hyperpod-incident-rca skill "
            f"should run in audit mode: discover open fault chains in "
            f"list-cluster-events (7-day window), classify each, and emit "
            f"Resolved / Monitor / Escalate per classification rules. If no "
            f"open chains exist, emit 'Suppress — periodic audit, no open "
            f"incidents'."
        ),
        "timestamp": now_iso,
        "service": "SageMakerHyperPod",
        "data": {
            "metadata": {
                "region": os.environ.get("AWS_REGION", "unknown"),
                "account": os.environ.get("AWS_ACCOUNT_ID", "unknown"),
                "detailType": "HyperPod Periodic Audit",
                "clusterName": cluster_name,
                "triggerMode": "audit",
            },
            "originalEvent": {
                "source": "hyperpod-devops-agent-periodic-audit",
                "detail-type": "HyperPod Periodic Audit",
                "time": now_iso,
                "detail": {
                    "ClusterName": cluster_name,
                    "Mode": "audit",
                },
            },
        },
    }


def _post(webhook_url: str, secret: str, payload: dict) -> None:
    body = json.dumps(payload).encode("utf-8")
    timestamp = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.000Z")
    signature = base64.b64encode(
        hmac.new(
            secret.encode("utf-8"),
            f"{timestamp}:{body.decode('utf-8')}".encode("utf-8"),
            hashlib.sha256,
        ).digest()
    ).decode("utf-8")

    request = urllib.request.Request(
        webhook_url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "x-amzn-event-timestamp": timestamp,
            "x-amzn-event-signature": signature,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as resp:
            print(f"webhook response status={resp.status} body={resp.read(512)!r}")
    except HTTPError as e:
        print(f"webhook HTTP error status={e.code} body={e.read()!r}")
        raise
    except URLError as e:
        print(f"webhook URL error: {e}")
        raise


def lambda_handler(event, context):
    cluster_name = os.environ.get("CLUSTER_NAME", "unknown-cluster")
    payload = _build_payload(cluster_name)
    print(f"periodic audit: cluster={cluster_name!r} incidentId={payload['incidentId']}")

    webhook_url, secret = _load_webhook_credentials()
    _post(webhook_url, secret, payload)
    return {"statusCode": 200, "body": json.dumps({"incidentId": payload["incidentId"]})}

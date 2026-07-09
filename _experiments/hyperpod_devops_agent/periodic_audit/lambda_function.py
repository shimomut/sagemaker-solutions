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
  WEBHOOK_SECRET_ARN               ARN of the Secrets Manager secret holding
                                   {"url": "...", "secret": "..."} (shared with bridge)
  CLUSTER_NAME                     Cluster the audit covers (purely informational —
                                   included in the synthetic payload metadata; the
                                   skill rediscovers clusters from describe-cluster
                                   on its own)
  K8S_CHECKS_ENABLED               "true" / "false" — master switch for the
                                   Kubernetes-state checks in the skill. When false,
                                   no k8sChecks block is emitted and the skill's
                                   audit-mode logic skips kubectl inspection.
  CRASHLOOP_HOURS_THRESHOLD        Escalate if any Pod is in CrashLoopBackOff for
                                   more than this many hours.
  NOT_READY_NODE_PERCENT_THRESHOLD Escalate if this percent or more of nodes are
                                   NotReady for the required duration.
  NOT_READY_DURATION_MINUTES       Minimum duration a node must be NotReady before
                                   it counts toward the percent threshold.
  IGNORE_NAMESPACES                Comma-separated. Pods in these namespaces are
                                   skipped entirely.
  SYSTEM_NAMESPACES                Comma-separated. CrashLoop verdicts on pods in
                                   these namespaces are tagged "system-workload".
                                   Must not overlap with IGNORE_NAMESPACES.
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


def _parse_namespace_list(env_name: str) -> list[str]:
    """Parse a comma-separated env var into a de-duplicated, trimmed list."""
    raw = os.environ.get(env_name, "")
    seen: dict[str, None] = {}
    for token in raw.split(","):
        tok = token.strip()
        if tok:
            seen[tok] = None
    return list(seen.keys())


def _build_k8s_checks_block() -> dict | None:
    """Assemble the structured k8sChecks block or return None if disabled.

    Validates that IGNORE_NAMESPACES and SYSTEM_NAMESPACES do not overlap.
    Raising here (rather than silently letting one win) is intentional —
    the skill classifies pods by set-membership lookup, and an ambiguous
    membership would produce inconsistent verdicts. Failing the audit
    invocation surfaces the misconfiguration in the Lambda logs.
    """
    enabled = os.environ.get("K8S_CHECKS_ENABLED", "true").strip().lower()
    if enabled not in ("true", "1", "yes", "on"):
        return None

    ignore = _parse_namespace_list("IGNORE_NAMESPACES")
    system = _parse_namespace_list("SYSTEM_NAMESPACES")
    overlap = sorted(set(ignore) & set(system))
    if overlap:
        raise ValueError(
            f"IGNORE_NAMESPACES and SYSTEM_NAMESPACES must not overlap; "
            f"conflicting entries: {overlap}. Fix the CFN parameters and redeploy."
        )

    return {
        "enabled": True,
        "crashLoopHoursThreshold": int(os.environ.get("CRASHLOOP_HOURS_THRESHOLD", "4")),
        "notReadyNodePercentThreshold": int(os.environ.get("NOT_READY_NODE_PERCENT_THRESHOLD", "10")),
        "notReadyDurationMinutes": int(os.environ.get("NOT_READY_DURATION_MINUTES", "15")),
        "ignoreNamespaces": ignore,
        "systemNamespaces": system,
    }


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


def _build_payload(cluster_name: str, k8s_checks: dict | None) -> dict:
    now_iso = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.000Z")
    now_compact = datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    incident_id = f"hyperpod-audit-{now_compact}"
    metadata = {
        "region": os.environ.get("AWS_REGION", "unknown"),
        "account": os.environ.get("AWS_ACCOUNT_ID", "unknown"),
        "detailType": "HyperPod Periodic Audit",
        "clusterName": cluster_name,
        "triggerMode": "audit",
    }
    if k8s_checks is not None:
        metadata["k8sChecks"] = k8s_checks
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
            "metadata": metadata,
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
    k8s_checks = _build_k8s_checks_block()
    payload = _build_payload(cluster_name, k8s_checks)
    print(
        f"periodic audit: cluster={cluster_name!r} incidentId={payload['incidentId']} "
        f"k8sChecks={'enabled' if k8s_checks else 'disabled'}"
    )

    webhook_url, secret = _load_webhook_credentials()
    _post(webhook_url, secret, payload)
    return {"statusCode": 200, "body": json.dumps({"incidentId": payload["incidentId"]})}

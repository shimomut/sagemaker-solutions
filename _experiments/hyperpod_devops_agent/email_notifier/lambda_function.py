"""Format DevOps Agent investigation events into a human-readable email and
send via SES.

Triggered by an EventBridge rule on `source: aws.aidevops`. The Lambda reads
the investigation event, fetches the verdict symptom + per-resource symptoms
from the agent's journal, and sends a single email per investigation lifecycle
transition to the configured SES recipients.

Verdicts whose title starts with "Triage verdict: Suppress" are skipped to
avoid email noise from the periodic audit firing on a healthy cluster (the
scheduled trigger fires every 15 min and produces a Suppress verdict when
nothing is happening).

Configuration via env vars:
  EMAIL_SENDER          - SES-verified From address. Required.
  EMAIL_RECIPIENTS      - Comma-separated To addresses. Required.
  EMAIL_DETAIL_TYPES    - Comma-separated allowlist of detail-types to send on
                          (default: all). DevOps Agent emits "Investigation
                          Created", "Investigation Updated", "Investigation
                          Closed" — limit to the ones you want to be paged on.
  CONSOLE_URL_TEMPLATE  - Optional template that resolves an investigation URL
                          from the event id. Uses %token% placeholders (%region%,
                          %account%, %investigation_id%). Defaults to Agent Space console.
  SKIP_VERDICT_PREFIXES - Comma-separated verdict-title prefixes to skip
                          (default: "Suppress").
"""
import datetime
import json
import os

import boto3


_ses_client = None
_devops_client = None


def _ses():
    global _ses_client
    if _ses_client is None:
        _ses_client = boto3.client("ses")
    return _ses_client


def _devops():
    global _devops_client
    if _devops_client is None:
        _devops_client = boto3.client("devops-agent")
    return _devops_client


def _skip_verdict_prefixes() -> list[str]:
    raw = os.environ.get("SKIP_VERDICT_PREFIXES", "Suppress")
    return [tok.strip() for tok in raw.split(",") if tok.strip()]


def _fetch_verdict_and_summary(event: dict) -> tuple[str | None, str | None]:
    """Return (verdict_title, full_description) from the investigation's
    verdict symptom, or (None, None) if it can't be located.

    The verdict symptom is identified by a title that starts with
    "Triage verdict:" — the hyperpod-incident-rca skill always emits one as
    the first symptom.
    """
    detail = event.get("detail", {})
    agent_space_id = detail.get("agentSpaceId") or detail.get("agentspaceId")
    task_id = detail.get("taskId") or detail.get("backlogTaskId")
    if not agent_space_id or not task_id:
        return None, None

    try:
        task = _devops().get_backlog_task(agentSpaceId=agent_space_id, taskId=task_id)["task"]
        execution_id = task.get("executionId")
        if not execution_id:
            return None, None

        # Paginate journal records — verdict symptom is one record among many.
        paginator = _devops().get_paginator("list_journal_records")
        for page in paginator.paginate(agentSpaceId=agent_space_id, executionId=execution_id):
            for record in page.get("records", []):
                if record.get("recordType") != "symptom":
                    continue
                try:
                    s = json.loads(record.get("content", "{}"))
                except (ValueError, TypeError):
                    continue
                title = s.get("title", "")
                if title.startswith("Triage verdict"):
                    return title, s.get("description", "")
    except Exception as e:
        print(f"verdict lookup failed: {e!r}")
    return None, None


def _recipients() -> list[str]:
    raw = os.environ.get("EMAIL_RECIPIENTS", "")
    return [tok.strip() for tok in raw.split(",") if tok.strip()]


def _allowed_detail_types() -> set[str] | None:
    raw = os.environ.get("EMAIL_DETAIL_TYPES", "")
    tokens = {tok.strip() for tok in raw.split(",") if tok.strip()}
    return tokens or None


def _console_url(event: dict) -> str:
    template = os.environ.get("CONSOLE_URL_TEMPLATE", "")
    if not template:
        return ""
    replacements = {
        "%region%": event.get("region", ""),
        "%account%": event.get("account", ""),
        "%investigation_id%": event.get("detail", {}).get("investigationId") or event.get("detail", {}).get("taskId", ""),
    }
    result = template
    for token, value in replacements.items():
        result = result.replace(token, value or "")
    return result


def _priority_emoji(priority: str) -> str:
    # Single letter prefix instead of emoji — keeps the subject email-safe.
    return {"HIGH": "[H]", "MEDIUM": "[M]", "LOW": "[L]"}.get(priority.upper(), "[?]")


def _format_body_text(event: dict, fields: dict, verdict_title: str | None, verdict_description: str | None) -> str:
    lines = [
        f"DevOps Agent investigation update",
        f"================================",
        "",
        f"Action:        {event.get('detail-type', '')}",
        f"Priority:      {fields['priority'] or 'n/a'}",
        f"Title:         {fields['title']}",
        f"Investigation: {fields['investigationId'] or 'n/a'}",
        f"Account:       {event.get('account', 'n/a')}",
        f"Region:        {event.get('region', 'n/a')}",
        f"Timestamp:     {event.get('time', 'n/a')}",
    ]
    url = _console_url(event)
    if url:
        lines.append(f"Console URL:   {url}")
    lines.append("")
    if verdict_title:
        lines.append("Verdict")
        lines.append("-------")
        lines.append(verdict_title)
        lines.append("")
    if verdict_description:
        lines.append("Details")
        lines.append("-------")
        lines.append(verdict_description)
        lines.append("")
    description = fields["description"]
    if description and not verdict_description:
        lines.append("Description / summary")
        lines.append("---------------------")
        lines.append(description)
        lines.append("")
    return "\n".join(lines)


def _format_subject(event: dict, fields: dict, verdict_title: str | None) -> str:
    priority = fields["priority"]
    if verdict_title:
        return f"{_priority_emoji(priority)} {verdict_title}"
    title = fields["title"]
    action = event.get("detail-type", "").replace("Investigation ", "")
    return f"{_priority_emoji(priority)} HyperPod investigation {action.lower()}: {title}"


def _extract_detail_fields(event: dict) -> dict:
    """Normalize event detail fields regardless of the nesting structure.

    DevOps Agent's EventBridge events may use flat top-level keys or
    nest them under 'backlogTask' or similar. We try multiple paths.
    """
    detail = event.get("detail", {})
    task = detail.get("backlogTask") or detail.get("task") or {}
    return {
        "title": detail.get("title") or task.get("title") or "(no title)",
        "priority": detail.get("priority") or task.get("priority") or "",
        "investigationId": (
            detail.get("investigationId")
            or detail.get("taskId")
            or task.get("taskId")
            or ""
        ),
        "agentSpaceId": detail.get("agentSpaceId") or task.get("agentSpaceId") or "",
        "taskId": detail.get("taskId") or task.get("taskId") or "",
        "description": detail.get("description") or task.get("description") or "",
    }


def lambda_handler(event, context):
    detail_type = event.get("detail-type", "")
    detail = event.get("detail", {})
    print(f"received event detail-type={detail_type!r} id={event.get('id')!r} detail-keys={sorted(detail.keys())}")
    print(f"detail snapshot: {json.dumps(detail)[:500]}")

    allowed = _allowed_detail_types()
    if allowed and detail_type not in allowed:
        print(f"skipping: detail-type {detail_type!r} not in allowlist {sorted(allowed)}")
        return {"statusCode": 200, "body": json.dumps({"skipped": True, "reason": "detail-type-not-in-allowlist"})}

    # Pull the verdict symptom out of the agent's journal. Filter on prefix.
    verdict_title, verdict_description = _fetch_verdict_and_summary(event)
    if verdict_title:
        bare = verdict_title.replace("Triage verdict:", "").strip()
        for prefix in _skip_verdict_prefixes():
            if bare.startswith(prefix):
                print(f"skipping: verdict {bare!r} starts with skip-prefix {prefix!r}")
                return {"statusCode": 200, "body": json.dumps({"skipped": True, "reason": f"verdict-prefix-{prefix}"})}

    fields = _extract_detail_fields(event)

    recipients = _recipients()
    if not recipients:
        raise RuntimeError("EMAIL_RECIPIENTS is empty — refusing to send")
    sender = os.environ.get("EMAIL_SENDER")
    if not sender:
        raise RuntimeError("EMAIL_SENDER is unset")

    subject = _format_subject(event, fields, verdict_title)
    body = _format_body_text(event, fields, verdict_title, verdict_description)
    print(f"sending email from={sender!r} to={recipients} subject={subject!r} bytes={len(body)}")

    resp = _ses().send_email(
        Source=sender,
        Destination={"ToAddresses": recipients},
        Message={
            "Subject": {"Data": subject, "Charset": "UTF-8"},
            "Body": {"Text": {"Data": body, "Charset": "UTF-8"}},
        },
    )
    print(f"ses MessageId={resp['MessageId']}")
    return {"statusCode": 200, "body": json.dumps({"messageId": resp["MessageId"]})}

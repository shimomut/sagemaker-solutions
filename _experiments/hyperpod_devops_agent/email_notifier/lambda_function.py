"""Format DevOps Agent investigation events into a human-readable email and
send via SES.

Triggered by an EventBridge rule on `source: aws.aidevops`. The Lambda reads
the investigation event, extracts the title, priority, verdict, and any
agent-produced summary, then sends a single email per investigation lifecycle
transition (created / updated / closed) to the configured SES recipients.

Configuration via env vars:
  EMAIL_SENDER          - SES-verified From address. Required.
  EMAIL_RECIPIENTS      - Comma-separated To addresses. Required.
  EMAIL_DETAIL_TYPES    - Comma-separated allowlist of detail-types to send on
                          (default: all). DevOps Agent emits "Investigation
                          Created", "Investigation Updated", "Investigation
                          Closed" — limit to the ones you want to be paged on.
  CONSOLE_URL_TEMPLATE  - Optional template that resolves an investigation URL
                          from the event id. Defaults to the Agent Space console.
"""
import datetime
import json
import os

import boto3


_ses_client = None


def _ses():
    global _ses_client
    if _ses_client is None:
        _ses_client = boto3.client("ses")
    return _ses_client


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
    return template.format(
        region=event.get("region", ""),
        account=event.get("account", ""),
        investigation_id=event.get("detail", {}).get("investigationId", ""),
    )


def _priority_emoji(priority: str) -> str:
    # Single letter prefix instead of emoji — keeps the subject email-safe.
    return {"HIGH": "[H]", "MEDIUM": "[M]", "LOW": "[L]"}.get(priority.upper(), "[?]")


def _format_subject(event: dict) -> str:
    detail = event.get("detail", {})
    priority = detail.get("priority", "")
    title = detail.get("title", "(no title)")
    action = event.get("detail-type", "").replace("Investigation ", "")
    return f"{_priority_emoji(priority)} HyperPod investigation {action.lower()}: {title}"


def _format_body_text(event: dict) -> str:
    detail = event.get("detail", {})
    lines = [
        f"DevOps Agent investigation update",
        f"================================",
        "",
        f"Action:        {event.get('detail-type', '')}",
        f"Priority:      {detail.get('priority', 'n/a')}",
        f"Title:         {detail.get('title', '(no title)')}",
        f"Investigation: {detail.get('investigationId', 'n/a')}",
        f"Account:       {event.get('account', 'n/a')}",
        f"Region:        {event.get('region', 'n/a')}",
        f"Timestamp:     {event.get('time', 'n/a')}",
    ]
    url = _console_url(event)
    if url:
        lines.append(f"Console URL:   {url}")
    lines.append("")
    description = detail.get("description") or detail.get("summary") or ""
    if description:
        lines.append("Description / summary")
        lines.append("---------------------")
        lines.append(description)
        lines.append("")
    verdict = detail.get("verdict") or detail.get("triageVerdict")
    if verdict:
        lines.append("Verdict")
        lines.append("-------")
        lines.append(str(verdict))
        lines.append("")
    recommendations = detail.get("recommendations") or detail.get("recommendedActions")
    if recommendations:
        lines.append("Recommended actions (operator runs these)")
        lines.append("-----------------------------------------")
        if isinstance(recommendations, list):
            for i, rec in enumerate(recommendations, 1):
                lines.append(f"  {i}. {rec}")
        else:
            lines.append(str(recommendations))
        lines.append("")
    lines.append("")
    lines.append("Raw event (for debugging):")
    lines.append(json.dumps(event, default=str, indent=2))
    return "\n".join(lines)


def lambda_handler(event, context):
    detail_type = event.get("detail-type", "")
    print(f"received event detail-type={detail_type!r} id={event.get('id')!r}")

    allowed = _allowed_detail_types()
    if allowed and detail_type not in allowed:
        print(f"skipping: detail-type {detail_type!r} not in allowlist {sorted(allowed)}")
        return {"statusCode": 200, "body": json.dumps({"skipped": True, "reason": "detail-type-not-in-allowlist"})}

    recipients = _recipients()
    if not recipients:
        raise RuntimeError("EMAIL_RECIPIENTS is empty — refusing to send")
    sender = os.environ.get("EMAIL_SENDER")
    if not sender:
        raise RuntimeError("EMAIL_SENDER is unset")

    subject = _format_subject(event)
    body = _format_body_text(event)
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

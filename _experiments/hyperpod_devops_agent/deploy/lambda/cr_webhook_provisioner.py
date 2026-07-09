"""CloudFormation custom resource: provision the DevOps Agent eventChannel webhook.

CloudFormation has no native path for the generic-webhook event channel:
`AWS::DevOpsAgent::Service` does not list `eventChannel` as a ServiceType, and
`AWS::DevOpsAgent::Association` with an EventChannel configuration does not
expose the generated webhook URL / HMAC secret as a Fn::GetAtt. So this custom
resource performs the same imperative flow the old scripts/02_provision_webhook.sh
did, and stashes the once-shown credentials into the Secrets Manager secret the
rest of the template references.

Resource properties (from the template):
  AgentSpaceId   - the Agent Space to attach the eventChannel to
  SecretArn      - Secrets Manager secret to receive {"url": ..., "secret": ...}

Lifecycle:
  Create/Update  - reuse an existing eventChannel association if present (its
                   HMAC secret is not recoverable, so we only re-populate the
                   URL in that case); otherwise register-service + associate-service
                   and write the fresh {url, secret} into the secret.
  Delete         - disassociate + deregister the eventChannel so the AgentSpace
                   (deleted after this resource, via DependsOn) has no leftover
                   associations blocking its own deletion.

The DevOps Agent API uses camelCase member names (mirrors the AWS CLI JSON shapes
in the original scripts), so boto3 kwargs are camelCase here.
"""
import json
import os

import boto3
import cfnresponse


_devops = boto3.client("devops-agent")
_secrets = boto3.client("secretsmanager")


def _find_event_channel_association(agent_space_id: str) -> dict | None:
    """Return an existing eventChannel association for the space, or None."""
    paginator_kwargs = {"agentSpaceId": agent_space_id}
    resp = _devops.list_associations(**paginator_kwargs)
    for assoc in resp.get("associations", []) or []:
        if (assoc.get("configuration") or {}).get("eventChannel") is not None:
            return assoc
    return None


def _write_secret(secret_arn: str, url: str, secret: str) -> None:
    _secrets.put_secret_value(
        SecretId=secret_arn,
        SecretString=json.dumps({"url": url, "secret": secret}),
    )
    print(f"wrote webhook url + secret into {secret_arn}")


def _provision(agent_space_id: str, secret_arn: str) -> dict:
    """Register + associate the eventChannel; populate the secret. Idempotent."""
    existing = _find_event_channel_association(agent_space_id)
    if existing is not None:
        assoc_id = existing.get("associationId", "")
        svc_id = existing.get("serviceId", "")
        print(f"reusing existing eventChannel association {assoc_id} (service {svc_id})")
        # The HMAC secret is only returned at associate time and cannot be
        # recovered. Re-populate the URL so downstream Lambdas at least have it;
        # a fresh secret requires disassociate + re-associate (teardown/redeploy).
        webhooks = _devops.list_webhooks(
            agentSpaceId=agent_space_id, associationId=assoc_id
        ).get("webhooks", []) or []
        url = (webhooks[0].get("webhookUrl") if webhooks else "") or ""
        if url:
            existing_secret = json.loads(
                _secrets.get_secret_value(SecretId=secret_arn)["SecretString"]
            ) if _secret_populated(secret_arn) else {}
            _write_secret(secret_arn, url, existing_secret.get("secret", ""))
        return {"AssociationId": assoc_id, "ServiceId": svc_id, "WebhookUrl": url}

    print("registering eventChannel service")
    svc_id = _devops.register_service(
        service="eventChannel",
        serviceDetails={"eventChannel": {"type": "webhook"}},
    )["serviceId"]
    print(f"registered service {svc_id}; associating to {agent_space_id}")
    resp = _devops.associate_service(
        agentSpaceId=agent_space_id,
        serviceId=svc_id,
        configuration={"eventChannel": {}},
    )
    assoc_id = resp["association"]["associationId"]
    url = resp["webhook"]["webhookUrl"]
    secret = resp["webhook"]["webhookSecret"]
    _write_secret(secret_arn, url, secret)
    return {"AssociationId": assoc_id, "ServiceId": svc_id, "WebhookUrl": url}


def _secret_populated(secret_arn: str) -> bool:
    try:
        _secrets.get_secret_value(SecretId=secret_arn)
        return True
    except _secrets.exceptions.ResourceNotFoundException:
        return False


def _deprovision(agent_space_id: str) -> None:
    """Disassociate + deregister every eventChannel on the space. Best-effort."""
    existing = _find_event_channel_association(agent_space_id)
    while existing is not None:
        assoc_id = existing.get("associationId", "")
        svc_id = existing.get("serviceId", "")
        try:
            _devops.disassociate_service(
                agentSpaceId=agent_space_id, associationId=assoc_id
            )
            print(f"disassociated eventChannel association {assoc_id}")
        except Exception as e:  # noqa: BLE001 - best-effort teardown
            print(f"disassociate failed for {assoc_id}: {e!r}")
        if svc_id:
            try:
                _devops.deregister_service(serviceId=svc_id)
                print(f"deregistered eventChannel service {svc_id}")
            except Exception as e:  # noqa: BLE001 - best-effort teardown
                print(f"deregister failed for {svc_id}: {e!r}")
        nxt = _find_event_channel_association(agent_space_id)
        # Guard against an association that refuses to delete so we don't spin.
        if nxt is not None and nxt.get("associationId") == assoc_id:
            print(f"association {assoc_id} still present after disassociate; stopping")
            break
        existing = nxt


def handler(event, context):
    request_type = event.get("RequestType")
    props = event.get("ResourceProperties", {}) or {}
    agent_space_id = props.get("AgentSpaceId", "")
    secret_arn = props.get("SecretArn", "")
    physical_id = event.get("PhysicalResourceId") or f"webhook-{agent_space_id}"

    print(f"RequestType={request_type} agentSpaceId={agent_space_id!r} secretArn={secret_arn!r}")

    try:
        if request_type == "Delete":
            if agent_space_id:
                _deprovision(agent_space_id)
            cfnresponse.send(event, context, cfnresponse.SUCCESS, {}, physical_id)
            return

        # Create or Update
        if not agent_space_id or not secret_arn:
            raise ValueError("AgentSpaceId and SecretArn are required properties")
        data = _provision(agent_space_id, secret_arn)
        cfnresponse.send(event, context, cfnresponse.SUCCESS, data, physical_id)
    except Exception as e:  # noqa: BLE001 - must always signal CFN
        print(f"ERROR: {e!r}")
        cfnresponse.send(
            event, context, cfnresponse.FAILED, {"Error": str(e)}, physical_id
        )

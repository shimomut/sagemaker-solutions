# HyperPod x AWS DevOps Agent — experiment

Experiment: wire SageMaker HyperPod (EKS first, Slurm later) into [AWS DevOps Agent](https://docs.aws.amazon.com/devopsagent/) so the agent can monitor cluster health, investigate failures, and drive remediation.

## What's here

- `docs/` — DevOps Agent user guide and API reference PDFs (git-ignored). Extracted `.txt` siblings are produced by `make extract-docs` for searching with `grep`.
- `extract_pdf.py` — PDF -> text via `pypdf`.
- `Makefile` — `make venv`, `make extract-docs`, `make clean`.

```bash
make venv          # create .venv and install pypdf
make extract-docs  # docs/*.pdf -> docs/*.txt (page markers included)
```

## Notes from the docs (anchor for design decisions)

DevOps Agent is organized around **Agent Spaces** (logical containers for accounts, integrations, permissions). Production operations breaks into:

- **Autonomous incident response** — kicked off by alerts/tickets/webhooks. The agent triages (link / skip / proceed), correlates telemetry across the topology, identifies root cause, and proposes a mitigation plan.
- **Proactive incident prevention** — weekly cross-incident analysis that surfaces recommendations across observability / infra / governance / code.
- **On-demand DevOps tasks** — natural-language chat over the topology.

Three relevant integration surfaces for us:

| Surface | Direction | Use for HyperPod |
| --- | --- | --- |
| **Webhooks** (generic, HMAC-signed) | _Into_ the agent | Trigger an investigation from any HyperPod signal we choose (cluster events, K8s events, custom alarms). |
| **EventBridge** events `source: aws.aidevops` | _From_ the agent | React to investigation lifecycle (Created / In Progress / Completed / Failed / Timed Out / Cancelled / Skipped / Linked) — e.g., post to Slack, open a ticket, fan out to a remediation Lambda. |
| **Skills** (modular instruction sets) | Inside the agent | Encode HyperPod-specific runbooks (node replacement, FSx checks, NCCL triage) and skip-criteria for noisy events. |

Built-in observability integrations include CloudWatch, Datadog, Dynatrace, Grafana, New Relic, Splunk. CloudWatch is the natural fit since HyperPod control-plane events and node logs already land there.

## Likely architecture (first sketch — not committed)

```
   HyperPod EKS cluster
       │
       │  SageMaker ListClusterEvents       ─┐
       │  EventBridge (HyperPod events)     ─┤
       │  CloudWatch Logs (control/data plane) ─┤───► (filter / shape) ───► DevOps Agent generic webhook
       │  K8s Events / Node conditions      ─┤                                       │
       │  CloudWatch Alarms (custom metrics)─┘                                       │
                                                                                     ▼
                                                              DevOps Agent investigation
                                                                                     │
                                                                                     ▼
                                                  EventBridge `aws.aidevops` lifecycle events
                                                                                     │
                          ┌─────────────────────────────┬────────────────────────────┘
                          ▼                             ▼
                  Slack / SES / ticket         Remediation Lambda
                                                  └─► reuse existing scripts
                                                      (hyperpod_replace_and_drain,
                                                       hyperpod_eks_auto_resume,
                                                       hyperpod_issue_report, …)
```

Two PoC scenarios that map cleanly onto existing repo plumbing:

1. **Node health → auto-replace.** EventBridge HyperPod event → small Lambda shapes it → DevOps Agent webhook → investigation completes → `aws.aidevops` "Investigation Completed" → remediation Lambda calls the replace-and-drain flow. Reuses [hyperpod_events/](../../hyperpod_events/) for the shaping and [hyperpod_replace_and_drain/](../../hyperpod_replace_and_drain/) for the action.
2. **Cluster anomaly → on-demand triage.** A CloudWatch Composite Alarm (e.g., FSx throughput drop or sustained NotReady nodes) fires → webhook → investigation produces an RCA → result is posted to Slack/SES.

## Open design questions

- **HyperPod EKS K8s signals**: does DevOps Agent's CloudWatch integration already pull container insights / EKS control-plane logs, or do we need to surface K8s node/pod events ourselves?
- **Skills authoring**: are we expected to write skills as files and upload via the Asset API, or only through the web app?
- **Quotas / cost**: the docs mention a monthly investigation rate limit ("hit the limit for the month") — need to check the Quotas chapter before designing high-volume triggers.
- **Region availability**: see "Supported Regions" page; need to confirm coverage in the regions we run HyperPod clusters.

## Next step

Decide which of the two PoC scenarios to build first, or whether to start with a discovery write-up that exhaustively maps every HyperPod signal source against DevOps Agent's ingestion options.

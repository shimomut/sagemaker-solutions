# HyperPod Mental Model — New Findings (YYYY-MM-DD)

<!--
Copy this file to  hyperpod-new-knowledge-<YYYY-MM-DD>.md  to start a session's
findings. This is the INBOX (staging), not the source of truth. Capture fast;
curation happens at merge time. See ../README.md for the full lifecycle.
Replace the date above and delete the parts you don't use.
-->

Findings from _<what you were doing — e.g. validating the mental model against a
live cluster while building X, debugging Y>_. Validating claims in
[`../hyperpod-mental-model.md`](../hyperpod-mental-model.md).

## Test environment

<!-- Make findings reproducible. Omit rows/columns that don't apply. -->

| Cluster | Orchestrator | ARN suffix | `NodeProvisioningMode` |
|---|---|---|---|
| `<name>` | Slurm / EKS | `cluster/<id>` | Continuous / OnStart |

Account `<id>`, region `<region>`. Call scope: <read-only (`describe*`/`list*`,
read-only SSM) / mutating>. <Note any cross-checks, e.g. against the botocore
SageMaker service model.>

## Confirmations (main doc held under test)

<!-- Claims that held. Cite the section/line in the main doc. Tag orchestrator. -->

1. **<claim>** — <evidence: the call, the response shape, where the main doc
   says it (line ~NNN)>. <Orchestrator tag if relevant.>

## Proposed edits to the main doc

<!-- Gaps or corrections to fold in. For each: WHERE it goes + proposed wording. -->

### 1. <short title>

**Where:** <section / line in hyperpod-mental-model.md or a supplemental doc>

**Gap:** <what's missing or wrong>

**Proposed wording:** <the sentence(s) to add or replace>

## New topics (not yet covered)

<!-- Subjects the main doc lacks. Flag candidates for a new mental-model/ doc. -->

- **<topic>** — <what it is, why it deserves coverage, candidate supplemental
  doc name, e.g. `mental-model/hyperpod-<topic>.md`>.

## Not yet verified (kept honest)

<!-- Things you did NOT exercise this session. Prevents over-reading the above. -->

- <claim that remains untested — e.g. detection→recovery flow, on-node SSM
  claims, EventBridge delivery path>.

## Open questions

<!-- Still unclear. These become "Things still unclear" in the main doc at merge. -->

- <question>

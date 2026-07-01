# Ideas + Questions

Scratchpad. Just write. Title + a couple of lines + any relevant IDs.

## Bridge misses `EventMetadata.Cluster.FailureMessage`

Bridge only reads `EventMetadata.Instance.FailureMessage`. Cluster-level events put it under `EventMetadata.Cluster.FailureMessage`. Fix: walk all subtrees under `EventMetadata`.

Investigation: `e281cd02-2df7-4245-8249-5860f4dd7e4a`
EventId: `127b07cf-9f00-4bdf-801e-11481419c562`


## Getting Warning "1 node(s) lost orchestration-ready status" when scaling down

I manually initiated scaling down by calling UpdateCluster API. Make sure the DevOps Agent recognize it and triage correctly.

Investigation: `e281cd02-2df7-4245-8249-5860f4dd7e4a`


## We should test real repeated lifecycle script errors

repeated lifecycle script errors is one of typical issues we should notify.
Let's modify the lifecycle script so that it fails, then replace multiple instances. Instance replacements should fail and keep retrying. Check what happens.


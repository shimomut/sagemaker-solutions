"""Ray Data: a small batch processing pipeline.

Ray Data is Ray's distributed dataset library. It streams data through a chain of
operators, running each one as Ray tasks across the cluster, so a dataset larger
than any single node's memory still flows through.

The point of this example is the shape of a pipeline, not the arithmetic:

    read -> map_batches -> filter -> groupby.aggregate

It is sized for a small CPU cluster deliberately. Ray Data asks for about 1 CPU
per concurrent task, so on a 3-CPU cluster a wide shuffle spends most of its time
backpressured. Raise ROWS and BLOCKS once you have more workers.

The groupby below is also what makes this example demand a Ray cluster whose nodes
report more than 1 CPU. A hash shuffle runs HashShuffleAggregator *actors*, and an
actor holds its resources for its whole life rather than for the length of a task.
Each takes 0.25 CPU, one lands per node, and a Filter task asking for a whole CPU
then fits nowhere: Ray logs "tasks with infeasible resource requests" and the job
sits at 0/1 indefinitely, because nothing will ever free up. The example manifests
give each pod `num-cpus: "2"` for exactly this reason.

Run it with:

    ray job submit --working-dir . -- python data_job.py
"""

import ray
import ray.data
import numpy as np
from ray.data.expressions import col

ROWS = 50_000
BLOCKS = 8

# 1. Create a dataset. `range` stands in for a real source: Ray Data reads
#    Parquet, CSV, JSON, images, and S3 URIs with the same downstream API, for
#    example ray.data.read_parquet("s3://bucket/prefix/").
#
#    A block is Ray Data's unit of parallelism. Operators run one task per block,
#    so the block count caps how much of the cluster one stage can use. Ray Data
#    chooses a count; override_num_blocks forces one.
dataset = ray.data.range(ROWS, override_num_blocks=BLOCKS)
print(f"created a dataset of {dataset.count()} rows")


# 2. Transform. map_batches hands each task a whole batch, as a dict of numpy
#    arrays here, which is why vectorised work belongs in map_batches rather than
#    in a per-row map.
def add_features(batch):
    value = batch["id"]
    return {
        "id": value,
        "bucket": value % 4,
        "score": np.sin(value / 1000.0) * 100,
    }


# Everything above is lazy. Ray Data builds a plan and fuses the operators, then
# runs them when something consumes rows. materialize() is that something: it
# executes now and holds the blocks in the object store, so the two consumers
# below reuse this work instead of recomputing it.
featured = dataset.map_batches(add_features, batch_format="numpy").materialize()
print(f"materialized into {featured.num_blocks()} blocks")

# 3. Filter, then aggregate per group. groupby is a shuffle: rows for one key have
#    to meet on one task, so unlike map_batches it moves data between nodes.
#
#    filter takes expr= (a Ray Data expression) or fn= (a Python callable applied
#    per row). Prefer expr: it stays on the vectorised path, while fn calls back
#    into Python once per row, and Ray Data warns when you pass fn for something
#    expr could have expressed. Build the expression with col(); the older string
#    form, expr="score > 0", still works but is deprecated.
summary = (
    featured.filter(expr=col("score") > 0)
    .groupby("bucket")
    .aggregate(
        ray.data.aggregate.Count(),
        ray.data.aggregate.Mean("score"),
        ray.data.aggregate.Max("score"),
    )
    .take_all()
)

print("\nper-bucket summary (positive scores only)")
for row in sorted(summary, key=lambda r: r["bucket"]):
    print(
        f"  bucket {row['bucket']}: "
        f"count={row['count()']:>6} "
        f"mean={row['mean(score)']:.2f} "
        f"max={row['max(score)']:.2f}"
    )


# 4. Confirm the work really was distributed. Each task reports the node it ran
#    on, so the distinct node count shows the cluster was used and not just the
#    head pod.
def tag_node(batch):
    ip = ray.util.get_node_ip_address()
    return {"node": np.array([ip] * len(batch["id"]))}


nodes = featured.map_batches(tag_node, batch_format="numpy").unique("node")
print(f"\nmap tasks ran on {len(nodes)} node(s): {sorted(nodes)}")

# 5. Writing results works the same way, one file per block:
#       featured.write_parquet("s3://your-bucket/prefix/")
print("\ndone")

"""Ray Train: distributed training, and how it consumes Ray Data.

Ray Train runs one copy of your training function per worker, each as a Ray
actor, and gives that function a shard of the dataset. This example uses
DataParallelTrainer, the framework-agnostic trainer, so it needs nothing beyond
what the Ray image already has.

That choice is also the one caveat. DataParallelTrainer starts the workers, shards
the data, and collects reports, but it does not set up a collective backend, so
the workers here do not average gradients. Each fits its own shard and reports its
own loss. Swap in TorchTrainer for real data-parallel training: the training
function keeps this shape, and Ray Train additionally builds the torch process
group so DistributedDataParallel can synchronise gradients. TorchTrainer needs
torch in the image, or installed through runtime_env.

Run it with:

    ray job submit --working-dir . -- python train_job.py
"""

import numpy as np
import ray
import ray.data
import ray.train
from ray.train import FailureConfig, RunConfig, ScalingConfig

# Ray 2.55 ships two generations of the Train API side by side, with the same
# class names in both. `ray.train.RunConfig` and `ray.train.ScalingConfig` are the
# v2 versions, so the trainer has to come from the v2 package too; pairing them
# with `ray.train.data_parallel_trainer.DataParallelTrainer`, which is v1, fails
# validation with a confusing "should be an instance of ray.train.RunConfig,
# found ray.train.RunConfig". `ray.train.torch.TorchTrainer` needs no such care.
from ray.train.v2.api.data_parallel_trainer import DataParallelTrainer

NUM_WORKERS = 2
EPOCHS = 20
ROWS = 20_000

# The relationship the workers have to recover: y = 3x + 7, plus noise.
TRUE_WEIGHT, TRUE_BIAS = 3.0, 7.0


def train_loop_per_worker(config):
    """Runs once per worker. This is the function Ray Train distributes."""
    # Ray Train tells each worker who it is. Use the rank to decide what only one
    # worker should do, such as logging or writing a checkpoint.
    context = ray.train.get_context()
    rank, world_size = context.get_world_rank(), context.get_world_size()

    # get_dataset_shard returns this worker's slice of the dataset passed to the
    # trainer as datasets={"train": ...}. Sharding is Ray Data's job, so the
    # training function never sees the whole dataset.
    shard = ray.train.get_dataset_shard("train")

    weight, bias, learning_rate = 0.0, 0.0, config["learning_rate"]

    for epoch in range(config["epochs"]):
        seen, total_loss = 0, 0.0

        # iter_batches streams the shard. It never materialises the whole shard in
        # the worker, which is what lets training data exceed worker memory.
        for batch in shard.iter_batches(batch_size=256, batch_format="numpy"):
            x, y = batch["x"], batch["y"]

            prediction = weight * x + bias
            error = prediction - y

            # Plain SGD. A real trainer would let the framework do this step and
            # let the collective backend average gradients across workers.
            weight -= learning_rate * 2.0 * np.mean(error * x)
            bias -= learning_rate * 2.0 * np.mean(error)

            total_loss += float(np.sum(error**2))
            seen += len(x)

        loss = total_loss / max(seen, 1)

        # report is how a worker sends metrics back to the driver. Pass
        # checkpoint=... to save state as well; see the note at the bottom about
        # the shared storage that needs.
        #
        # Note that Trainer.fit() returns a Result whose .metrics is None unless a
        # report carried a checkpoint, so do not rely on it to read plain metrics
        # back. Printing from the worker is the simple way to see per-epoch
        # progress, and it is rank 0 only to keep the output readable.
        ray.train.report(
            {
                "epoch": epoch,
                "loss": loss,
                "weight": weight,
                "bias": bias,
                "rows_seen": seen,
                "rank": rank,
                "world_size": world_size,
            }
        )

        if rank == 0:
            print(
                f"  epoch {epoch}: loss={loss:8.4f} weight={weight:6.3f} "
                f"bias={bias:6.3f} rows={seen} (of {world_size} workers)"
            )


# Build the training data as a Ray Data dataset. Ray Train shards whatever it is
# given here, so read_parquet("s3://...") substitutes directly.
# x is scaled into [0, 1). Feature scale and learning rate have to suit each
# other: leaving x in the thousands makes the gradients explode and the loss run
# off to infinity within an epoch, which looks like a Ray problem but is not one.
def make_batch(batch):
    x = batch["id"].astype(np.float64) / ROWS
    noise = np.random.default_rng(0).normal(0, 0.05, size=len(x))
    return {"x": x, "y": TRUE_WEIGHT * x + TRUE_BIAS + noise}


train_dataset = ray.data.range(ROWS, override_num_blocks=8).map_batches(
    make_batch, batch_format="numpy"
)

trainer = DataParallelTrainer(
    train_loop_per_worker=train_loop_per_worker,
    train_loop_config={"epochs": EPOCHS, "learning_rate": 0.5},
    # One actor per worker, each holding these resources for the whole run. Ask
    # for more than the cluster has and the run waits instead of failing, so keep
    # NUM_WORKERS within your free CPU count. use_gpu=True asks for a GPU each.
    scaling_config=ScalingConfig(
        num_workers=NUM_WORKERS,
        use_gpu=False,
        resources_per_worker={"CPU": 1},
    ),
    datasets={"train": train_dataset},
    run_config=RunConfig(
        # Retry the run when a worker dies. The default is 0, so a single node
        # fault ends the run even though HyperPod recovered the node. Be liberal:
        # hardware faults are routine at cluster scale, and a retry resumes from
        # the last checkpoint rather than starting over. -1 retries forever.
        failure_config=FailureConfig(max_failures=3),
    ),
)

print(f"\ntraining on {NUM_WORKERS} workers, {EPOCHS} epochs")
result = trainer.fit()

print("\ntraining finished")
print(f"  target: weight={TRUE_WEIGHT}  bias={TRUE_BIAS}")
if result.metrics:
    print(f"  last report: {result.metrics}")
else:
    # Expected here: no report carried a checkpoint, so there is nothing for
    # Ray Train to attach the metrics to. See the epoch lines above instead.
    print("  metrics: reported per epoch above (Result.metrics needs a checkpoint)")
if result.error:
    print(f"  error: {result.error}")

# On checkpointing: ray.train.report(metrics, checkpoint=...) needs storage every
# worker can reach, because any worker may write one. Set
# RunConfig(storage_path="s3://your-bucket/runs/") or point it at a shared file
# system such as FSx for Lustre. A local path fails on a multi-node cluster.
# HyperPod also offers managed tiered checkpointing, which writes to cluster CPU
# memory first and persists to S3 in the background, so you can checkpoint far
# more often than S3 alone would allow.

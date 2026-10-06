"""Ray Serve: an HTTP service built from composed deployments.

Ray Serve turns Python classes into HTTP-addressable deployments. Each deployment
scales its replicas independently, and one deployment calls another through a
handle rather than over the network, so a pipeline stays in-process where it can.

This app has two deployments to show that composition:

    HTTP -> Router (ingress, 1 replica) -> Scorer (2 replicas, autoscaling)

It stands in for the usual LLM shape, where the ingress does tokenisation or
request validation and the downstream deployment holds the model. Nothing here
needs a library the Ray image lacks.

Two ways to run it, both verified:

  * As a RayService, which creates and manages its own Ray cluster. KubeRay reads
    the `app` object below through the import_path in serveConfigV2.

  * On a Ray cluster you already have, with `serve.run()`:
        ray job submit --working-dir . -- python serve_app.py
"""

import numpy as np
import ray
from ray import serve
from starlette.requests import Request


@serve.deployment(
    # Ray Serve adds and removes replicas of this deployment on its own, between
    # these bounds. Scaling replicas is not the same as scaling the cluster: if
    # the cluster has no free CPU, new replicas stay pending until it does.
    autoscaling_config={
        "min_replicas": 2,
        "max_replicas": 4,
        "target_ongoing_requests": 5,
    },
    # Deliberately fractional. Ray Serve replicas are Ray actors, and asking for
    # a whole CPU each would not fit a small cluster alongside the ingress.
    ray_actor_options={"num_cpus": 0.25},
)
class Scorer:
    """Stands in for a model. Real deployments load weights in __init__."""

    def __init__(self, weight: float, bias: float):
        self.weight, self.bias = weight, bias
        # A replica's identity is useful for showing that requests spread out.
        self.replica = serve.get_replica_context().replica_tag
        self.node = ray.util.get_node_ip_address()

    def score(self, values: list) -> dict:
        array = np.asarray(values, dtype=np.float64)
        return {
            "predictions": (self.weight * array + self.bias).tolist(),
            "served_by": {"replica": self.replica, "node": self.node},
        }


@serve.deployment(num_replicas=1, ray_actor_options={"num_cpus": 0.25})
class Router:
    """The ingress. Its __call__ handles the raw HTTP request."""

    def __init__(self, scorer):
        # `scorer` arrives as a DeploymentHandle, not an instance. Calls through it
        # are routed to whichever replica is free, and they return a future.
        self.scorer = scorer

    async def __call__(self, request: Request) -> dict:
        try:
            body = await request.json()
        except Exception:
            body = {}
        values = body.get("values", [1.0, 2.0, 3.0])

        # await the handle call to get the result. Serve load-balances across the
        # Scorer replicas for you.
        result = await self.scorer.score.remote(values)
        return {"input": values, **result}


# The deployment graph. bind() wires arguments and handles together without
# starting anything; `app` is what serve.run() or a RayService import_path takes.
app = Router.bind(Scorer.bind(weight=3.0, bias=7.0))


if __name__ == "__main__":
    # This path is for a Ray cluster that already exists: it deploys the app onto
    # the current cluster and leaves it serving after the job exits, which is what
    # `blocking=False` means. Use `serve.delete("default")` to remove it.
    #
    # A RayService does not need any of this. KubeRay applies serveConfigV2
    # itself, and manages upgrades by standing up a second cluster first.
    serve.run(app, blocking=False)
    print("deployed. the app is reachable on port 8000 of the head service:")
    print("  kubectl port-forward service/<cluster>-head-svc 8000:8000")
    print('  curl -s localhost:8000 -H "Content-Type: application/json" \\')
    print('       -d \'{"values": [1, 2, 10]}\'')

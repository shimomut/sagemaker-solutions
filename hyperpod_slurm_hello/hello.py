import os
import time

slurm_node_id = os.environ["SLURM_NODEID"]
slurm_local_id = os.environ["SLURM_LOCALID"]

i = 0
while True:
    print(f"node-id:{slurm_node_id} local-id:{slurm_local_id} : Hello {i}", flush=True)
    time.sleep(5)
    i+=1

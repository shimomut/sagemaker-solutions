# Run DDP with torchrun command. Can be run on multiple nodes. Use DistributedSampler for dataset.
# Based on https://pytorch.org/tutorials/intermediate/ddp_tutorial.html
# Usage: torchrun --nnodes=1 --nproc_per_node=4 --rdzv_id=100 --rdzv_backend=c10d --rdzv_endpoint=$MASTER_ADDR:29400 step3.py


import os

import torch
import torch.distributed as dist
import torch.nn as nn
import torch.optim as optim

from torch.nn.parallel import DistributedDataParallel as DDP


def print_node_info():
    print( 
        f"Node info:\n" +
        f"  Hostname : {os.uname()[1]}\n" +
        f"  RANK : {os.environ['RANK']}\n" +
        f"  WORLD_SIZE : {os.environ['WORLD_SIZE']}\n" +
        f"  LOCAL_RANK : {os.environ['LOCAL_RANK']}\n" +
        f"  LOCAL_WORLD_SIZE : {os.environ['LOCAL_WORLD_SIZE']}\n" +
        f"  torch.distributed.get_rank() : {torch.distributed.get_rank()}\n" +
        f"  torch.distributed.get_world_size() : {torch.distributed.get_world_size()}\n" +
        f"  torch.cuda.device_count() : {torch.cuda.device_count()}\n"
    )


class RandomDataset:
    def __getitem__(self, x):
        return torch.randn(10)

    def __len__(self):
        return 512


class ToyModel(nn.Module):
    def __init__(self):
        super(ToyModel, self).__init__()
        self.net1 = nn.Linear(10, 10)
        self.relu = nn.ReLU()
        self.net2 = nn.Linear(10, 5)

    def forward(self, x):
        return self.net2(self.relu(self.net1(x)))


def demo_basic():
    dist.init_process_group("nccl")
    print_node_info()

    rank = dist.get_rank()

    # preapre training dataset
    train_dataset = RandomDataset()
    train_data_sampler = torch.utils.data.distributed.DistributedSampler(
        train_dataset,
        num_replicas=torch.distributed.get_world_size(), 
        rank=torch.distributed.get_rank(),
    )
    train_data_loader = torch.utils.data.DataLoader(
        train_dataset, batch_size=16, sampler=train_data_sampler
    )

    # create model and move it to GPU with id rank
    device_id = rank % torch.cuda.device_count()
    model = ToyModel().to(device_id)
    ddp_model = DDP(model, device_ids=[device_id])

    loss_fn = nn.MSELoss()
    optimizer = optim.SGD(ddp_model.parameters(), lr=0.001)

    for data in train_data_loader:

        assert data.shape == (16,10) # (batch size, input shape)

        optimizer.zero_grad()
        outputs = ddp_model(data)
        labels = torch.randn(16, 5).to(device_id)
        loss_fn(outputs, labels).backward()
        optimizer.step()

    dist.destroy_process_group()

    print("Done.")


if __name__ == "__main__":
    demo_basic()
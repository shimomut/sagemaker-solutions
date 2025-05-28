#!/bin/bash

# Copy from the output of sinfo. You can include both worker nodes and login nodes
nodes="ip-10-1-16-188,ip-10-1-75-77,ip-10-1-79-4"

NODES=$( scontrol show hostnames $nodes  | sed 'N;s/\n/ /' )
echo $NODES

current_dir=$(pwd)
command="cd $current_dir && sudo bash add_users.sh"

for node in $NODES
do
        echo -e "SSH into $node"
        ssh $node $command
done
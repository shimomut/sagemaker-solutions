#!/bin/bash

# Original version: https://catalog.workshops.aws/sagemaker-hyperpod/en-US/07-tips-and-tricks/01-multi-user

set -x

# Prompt user to get the new user name.
read -p "Enter the new user name, i.e. 'sean': 
" USER

# Prompt user to get the user-ID.
read -p "Enter the user ID, i.e. '2001': 
" USER_ID

# create home directory as /fsx/<user>
# Create the new user on the head node
sudo useradd -u $USER_ID $USER -m -d /fsx/$USER --shell /bin/bash;

# add user to docker group
sudo usermod -aG docker ${USER}

# setup SSH Keypair
sudo -u $USER ssh-keygen -t rsa -q -f "/fsx/$USER/.ssh/id_rsa" -N ""
sudo -u $USER cat /fsx/$USER/.ssh/id_rsa.pub | sudo -u $USER tee /fsx/$USER/.ssh/authorized_keys

# add user to compute nodes
read -p "Number of compute nodes in your cluster, i.e. 8: 
" NUM_NODES
srun -N $NUM_NODES sudo useradd -u $USER_ID $USER -d /fsx/$USER --shell /bin/bash;

# add them as a sudoer
read -p "Do you want this user to be a sudoer? (y/N):
" SUDO
if [ "$SUDO" = "y" ]; then
        sudo usermod -aG sudo $USER
        sudo srun -N $NUM_NODES sudo usermod -aG sudo $USER
        echo -e "If you haven't already you'll need to run:\n\nsudo visudo /etc/sudoers\n\nChange the line:\n\n%sudo   ALL=(ALL:ALL) ALL\n\nTo\n\n%sudo   ALL=(ALL:ALL) NOPASSWD: ALL\n\nOn each node."
fi

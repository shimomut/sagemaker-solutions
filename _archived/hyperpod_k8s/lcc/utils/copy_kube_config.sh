#!/bin/bash

set -ex

# FIXME : LCC script is run as root. This script should be run as ubuntu user.

mkdir -p $HOME/.kube
sudo cp /etc/kubernetes/admin.conf $HOME/.kube/config
sudo chown $(id -u):$(id -g) $HOME/.kube/config

#!/bin/bash

set -ex

# https://kubernetes.io/docs/setup/production-environment/tools/kubeadm/install-kubeadm/


sudo apt-get -y -o DPkg::Lock::Timeout=120 update
sudo apt-get -y -o DPkg::Lock::Timeout=120 install apt-transport-https ca-certificates curl gpg

sudo install -m 0755 -d /etc/apt/keyrings

curl -fsSL https://pkgs.k8s.io/core:/stable:/v1.29/deb/Release.key | sudo gpg --yes --dearmor -o /etc/apt/keyrings/kubernetes-apt-keyring.gpg

echo 'deb [signed-by=/etc/apt/keyrings/kubernetes-apt-keyring.gpg] https://pkgs.k8s.io/core:/stable:/v1.29/deb/ /' | sudo tee /etc/apt/sources.list.d/kubernetes.list

sudo apt-get -y -o DPkg::Lock::Timeout=120 update
sudo apt-get -y -o DPkg::Lock::Timeout=120 install kubelet kubeadm kubectl
sudo apt-mark -o DPkg::Lock::Timeout=120 hold kubelet kubeadm kubectl

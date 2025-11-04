#!/bin/bash

set -e

LOG_FILE="/var/log/provision/provisioning.log"

mkdir -p "/var/log/provision"
touch "$LOG_FILE"

logger() {
  echo "$@" | stdbuf -oL -eL tee -a "$LOG_FILE"
  sync
}

logger "[start] on_create.sh"

stdbuf -oL -eL bash ./on_create_main.sh >> "$LOG_FILE" 2>&1
sync

logger "[stop] on_create.sh"

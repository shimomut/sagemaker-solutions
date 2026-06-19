#!/bin/bash
# Example shell script for `make run-shell-script`.
# Prints a few facts about the node it runs on.
set -euo pipefail

echo "Hostname: $(hostname)"
echo "Kernel:   $(uname -r)"
echo "Uptime:   $(uptime -p 2>/dev/null || uptime)"
echo "Args:     $*"

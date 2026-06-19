# HyperPod Multi-Node Command Runner Makefile

# Python interpreter used to bootstrap the venv. Override on the command line
# if your system uses a different name (e.g. `make venv PYTHON3=python3.13`).
PYTHON3 ?= python3.14

VENV_DIR    := .venv
VENV_PYTHON := $(VENV_DIR)/bin/python
VENV_PIP    := $(VENV_DIR)/bin/pip
VENV_STAMP  := $(VENV_DIR)/.installed

.PHONY: help venv run debug run-cluster test-node run-command \
        run-shell-script run-python-script clean test check-aws

# Default target
help:
	@echo "Available targets:"
	@echo "  venv              - Create local virtualenv ($(VENV_DIR)) from $(PYTHON3) and install dependencies"
	@echo "  run               - Run the multi-node command runner (interactive)"
	@echo "  run-cluster       - Run with a specific cluster"
	@echo "  run-command       - Run a single command on the cluster"
	@echo "  run-shell-script  - Run a local shell script on cluster nodes"
	@echo "  run-python-script - Run a local Python script on cluster nodes"
	@echo "  test-node         - Test SSM connectivity to one instance"
	@echo "  test              - Run basic import sanity check"
	@echo "  check-aws         - Verify AWS credentials are usable"
	@echo "  clean             - Clean up temporary files"
	@echo "  help              - Show this help message"

# Create the virtualenv and install dependencies. Setup only runs when the
# venv is missing or requirements.txt has changed — other targets depend on
# $(VENV_STAMP), so they're a no-op when everything is up to date.
venv: $(VENV_STAMP)

$(VENV_STAMP): requirements.txt
	@if [ ! -x "$(VENV_PYTHON)" ]; then \
		echo "Creating venv at $(VENV_DIR) using $(PYTHON3)..."; \
		$(PYTHON3) -m venv $(VENV_DIR); \
	fi
	@echo "Installing Python dependencies into $(VENV_DIR)..."
	$(VENV_PIP) install -r requirements.txt
	@touch $(VENV_STAMP)

# Run the tool
run: $(VENV_STAMP)
	@echo "Starting HyperPod Multi-Node Command Runner..."
	$(VENV_PYTHON) hyperpod_run_on_multi_nodes.py

# Run with debug mode
debug: $(VENV_STAMP)
	@echo "Starting HyperPod Multi-Node Command Runner (debug mode)..."
	$(VENV_PYTHON) hyperpod_run_on_multi_nodes.py --debug

# Run with specific cluster
run-cluster: $(VENV_STAMP)
	@echo "Usage: make run-cluster CLUSTER=your-cluster-name"
	@if [ -z "$(CLUSTER)" ]; then echo "Please specify CLUSTER=your-cluster-name"; exit 1; fi
	$(VENV_PYTHON) hyperpod_run_on_multi_nodes.py --cluster $(CLUSTER)

# Test SSM connectivity to a specific instance
test-node: $(VENV_STAMP)
	@echo "Usage: make test-node INSTANCE=i-1234567890abcdef0"
	@if [ -z "$(INSTANCE)" ]; then echo "Please specify INSTANCE=your-instance-id"; exit 1; fi
	$(VENV_PYTHON) hyperpod_run_on_multi_nodes.py --test-node $(INSTANCE)

# Run single command on cluster
run-command: $(VENV_STAMP)
	@echo "Usage: make run-command CLUSTER=your-cluster-name COMMAND='your-command'"
	@if [ -z "$(CLUSTER)" ]; then echo "Please specify CLUSTER=your-cluster-name"; exit 1; fi
	@if [ -z "$(COMMAND)" ]; then echo "Please specify COMMAND='your-command'"; exit 1; fi
	$(VENV_PYTHON) hyperpod_run_on_multi_nodes.py --cluster $(CLUSTER) --command "$(COMMAND)"

# Run a local shell script on every node (or one instance group).
# Example: make run-shell-script CLUSTER=your-cluster-name SCRIPT=examples/hello.sh [GROUP=worker1]
run-shell-script: $(VENV_STAMP)
	@echo "Example: make run-shell-script CLUSTER=your-cluster-name SCRIPT=examples/hello.sh [GROUP=worker1]"
	@if [ -z "$(CLUSTER)" ]; then echo "Please specify CLUSTER=your-cluster-name"; exit 1; fi
	@if [ -z "$(SCRIPT)" ]; then echo "Please specify SCRIPT=examples/hello.sh"; exit 1; fi
	$(VENV_PYTHON) hyperpod_run_on_multi_nodes.py --cluster $(CLUSTER) --script-file $(SCRIPT) $(if $(GROUP),--instance-group $(GROUP))

# Run a local Python script on every node (or one instance group).
# Requires python3 on each node.
# Example: make run-python-script CLUSTER=your-cluster-name SCRIPT=examples/hello.py [GROUP=worker1]
run-python-script: $(VENV_STAMP)
	@echo "Example: make run-python-script CLUSTER=your-cluster-name SCRIPT=examples/hello.py [GROUP=worker1]"
	@if [ -z "$(CLUSTER)" ]; then echo "Please specify CLUSTER=your-cluster-name"; exit 1; fi
	@if [ -z "$(SCRIPT)" ]; then echo "Please specify SCRIPT=examples/hello.py"; exit 1; fi
	$(VENV_PYTHON) hyperpod_run_on_multi_nodes.py --cluster $(CLUSTER) --python-script-file $(SCRIPT) $(if $(GROUP),--instance-group $(GROUP))

# Clean up
clean:
	@echo "Cleaning up temporary files..."
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -delete
	rm -rf .pytest_cache/ $(VENV_DIR)

# Basic test
test: $(VENV_STAMP)
	@echo "Running basic tests..."
	$(VENV_PYTHON) -c "import boto3, pexpect; print('Dependencies OK')"
	$(VENV_PYTHON) -c "from hyperpod_run_on_multi_nodes import HyperPodMultiNodeRunner; print('Import OK')"
	@echo "Tests passed!"

# Check AWS credentials
check-aws:
	@echo "Checking AWS credentials..."
	aws sts get-caller-identity
	@echo "AWS credentials OK!"

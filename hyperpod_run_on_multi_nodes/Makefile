# HyperPod Multi-Node Command Runner Makefile

.PHONY: help install run clean test run-shell-script run-python-script

# Default target
help:
	@echo "Available targets:"
	@echo "  install    - Install Python dependencies"
	@echo "  run        - Run the multi-node command runner"
	@echo "  clean      - Clean up temporary files"
	@echo "  test       - Run basic tests"
	@echo "  run-shell-script  - Run a local shell script on cluster nodes"
	@echo "  run-python-script - Run a local Python script on cluster nodes"
	@echo "  help       - Show this help message"

# Install dependencies
install:
	@echo "Installing Python dependencies..."
	pip install -r requirements.txt

# Run the tool
run:
	@echo "Starting HyperPod Multi-Node Command Runner..."
	python main.py

# Run with debug mode
debug:
	@echo "Starting HyperPod Multi-Node Command Runner (debug mode)..."
	python main.py --debug

# Run with specific cluster
run-cluster:
	@echo "Usage: make run-cluster CLUSTER=your-cluster-name"
	@if [ -z "$(CLUSTER)" ]; then echo "Please specify CLUSTER=your-cluster-name"; exit 1; fi
	python main.py --cluster $(CLUSTER)

# Test SSM connectivity to a specific instance
test-node:
	@echo "Usage: make test-node INSTANCE=i-1234567890abcdef0"
	@if [ -z "$(INSTANCE)" ]; then echo "Please specify INSTANCE=your-instance-id"; exit 1; fi
	python main.py --test-node $(INSTANCE)

# Run single command on cluster
run-command:
	@echo "Usage: make run-command CLUSTER=your-cluster-name COMMAND='your-command'"
	@if [ -z "$(CLUSTER)" ]; then echo "Please specify CLUSTER=your-cluster-name"; exit 1; fi
	@if [ -z "$(COMMAND)" ]; then echo "Please specify COMMAND='your-command'"; exit 1; fi
	python main.py --cluster $(CLUSTER) --command "$(COMMAND)"

# Run a local shell script on every node (or one instance group).
# Example: make run-shell-script CLUSTER=your-cluster-name SCRIPT=examples/hello.sh [GROUP=worker1]
run-shell-script:
	@echo "Example: make run-shell-script CLUSTER=your-cluster-name SCRIPT=examples/hello.sh [GROUP=worker1]"
	@if [ -z "$(CLUSTER)" ]; then echo "Please specify CLUSTER=your-cluster-name"; exit 1; fi
	@if [ -z "$(SCRIPT)" ]; then echo "Please specify SCRIPT=examples/hello.sh"; exit 1; fi
	python3 hyperpod_run_on_multi_nodes.py --cluster $(CLUSTER) --script-file $(SCRIPT) $(if $(GROUP),--instance-group $(GROUP))

# Run a local Python script on every node (or one instance group).
# The tool executes uploaded script content under `bash -s --`, so this target
# generates a small bash wrapper that pipes the .py file to `python3 -` via a
# heredoc. Requires python3 on each node.
# Example: make run-python-script CLUSTER=your-cluster-name SCRIPT=examples/hello.py [GROUP=worker1]
run-python-script:
	@echo "Example: make run-python-script CLUSTER=your-cluster-name SCRIPT=examples/hello.py [GROUP=worker1]"
	@if [ -z "$(CLUSTER)" ]; then echo "Please specify CLUSTER=your-cluster-name"; exit 1; fi
	@if [ -z "$(SCRIPT)" ]; then echo "Please specify SCRIPT=examples/hello.py"; exit 1; fi
	@WRAPPER=$$(mktemp); \
	trap "rm -f $$WRAPPER" EXIT; \
	{ echo "python3 - <<'__PYEOF__'"; cat $(SCRIPT); echo "__PYEOF__"; } > $$WRAPPER; \
	python3 hyperpod_run_on_multi_nodes.py --cluster $(CLUSTER) --script-file $$WRAPPER $(if $(GROUP),--instance-group $(GROUP))

# Clean up
clean:
	@echo "Cleaning up temporary files..."
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -delete
	rm -rf .pytest_cache/

# Basic test
test:
	@echo "Running basic tests..."
	python -c "import boto3, pexpect; print('Dependencies OK')"
	python -c "from main import HyperPodMultiNodeRunner; print('Import OK')"
	@echo "Tests passed!"

# Check AWS credentials
check-aws:
	@echo "Checking AWS credentials..."
	aws sts get-caller-identity
	@echo "AWS credentials OK!"
# HyperPod Multi-Node Command Runner Makefile

.PHONY: help install run clean test

# Default target
help:
	@echo "Available targets:"
	@echo "  install    - Install Python dependencies"
	@echo "  run        - Run the multi-node command runner"
	@echo "  clean      - Clean up temporary files"
	@echo "  test       - Run basic tests"
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

# List all running instances
list-instances:
	@echo "Listing all running EC2 instances..."
	python main.py --list-instances

# Run with specific cluster
run-cluster:
	@echo "Usage: make run-cluster CLUSTER=your-cluster-name"
	@if [ -z "$(CLUSTER)" ]; then echo "Please specify CLUSTER=your-cluster-name"; exit 1; fi
	python main.py --cluster $(CLUSTER)

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
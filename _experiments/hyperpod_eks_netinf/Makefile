# HyperPod EKS Network Interface Script Makefile

.PHONY: help install run clean test

help:
	@echo "Available targets:"
	@echo "  install    - Install Python dependencies"
	@echo "  run        - Run the network interface script (requires sudo)"
	@echo "  test       - Run basic syntax and import tests"
	@echo "  clean      - Clean up temporary files"

install:
	pip install -r requirements.txt

run:
	@echo "Running network interface script..."
	@echo "Note: This requires sudo privileges"
	sudo python3 hyperpod_eks_netinf.py

test:
	@echo "Running syntax check..."
	python3 -m py_compile hyperpod_eks_netinf.py
	@echo "Running import test..."
	python3 -c "import hyperpod_eks_netinf; print('Import successful')"

clean:
	find . -name "*.pyc" -delete
	find . -name "__pycache__" -type d -exec rm -rf {} +
	@echo "Cleaned up temporary files"
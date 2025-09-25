# HyperPod EKS Network Interface Script Makefile

.PHONY: help install run clean test verify-connectivity verify-interface move-and-verify

help:
	@echo "Available targets:"
	@echo "  install             - Install Python dependencies"
	@echo "  run                 - Run the network interface script (requires sudo)"
	@echo "  test                - Run basic syntax and import tests"
	@echo "  verify-connectivity - Verify internet connectivity of moved interfaces"
	@echo "  verify-interface    - Verify connectivity of specific interface (use INTERFACE=name)"
	@echo "  move-and-verify     - Move network interface and verify connectivity (requires sudo)"
	@echo "  clean               - Clean up temporary files"

install:
	pip install -r requirements.txt

run:
	@echo "Running network interface script..."
	@echo "Note: This requires sudo privileges"
	sudo python3 hyperpod_eks_netinf.py

test:
	@echo "Running syntax check..."
	python3 -m py_compile hyperpod_eks_netinf.py
	python3 -m py_compile verify_connectivity.py
	@echo "Running import test..."
	python3 -c "import hyperpod_eks_netinf; print('Main script import successful')"
	python3 -c "import verify_connectivity; print('Connectivity verifier import successful')"

verify-connectivity:
	@echo "Verifying internet connectivity of network interfaces..."
	@echo "This will auto-detect recently moved interfaces and test connectivity"
	python3 verify_connectivity.py --verbose --save-results

verify-interface:
	@if [ -z "$(INTERFACE)" ]; then \
		echo "Error: Please specify INTERFACE=<interface_name>"; \
		echo "Example: make verify-interface INTERFACE=eth2"; \
		exit 1; \
	fi
	@echo "Verifying connectivity for interface: $(INTERFACE)"
	python3 verify_connectivity.py --interface $(INTERFACE) --verbose --save-results

move-and-verify:
	@echo "Moving network interface and verifying connectivity..."
	@echo "Step 1: Moving network interface (requires sudo)..."
	sudo python3 hyperpod_eks_netinf.py
	@echo ""
	@echo "Step 2: Verifying connectivity..."
	python3 verify_connectivity.py --verbose --save-results

clean:
	find . -name "*.pyc" -delete
	find . -name "__pycache__" -type d -exec rm -rf {} +
	find . -name "connectivity_test_*.json" -delete
	@echo "Cleaned up temporary files and test results"
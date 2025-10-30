# ENI Dump Utility Makefile

.PHONY: help install run clean

help:
	@echo "Available targets:"
	@echo "  install    - Install Python dependencies"
	@echo "  run        - Run the script (requires VPC_ID environment variable)"
	@echo "  clean      - Remove generated files"
	@echo ""
	@echo "Usage examples:"
	@echo "  make install"
	@echo "  VPC_ID=vpc-12345678 make run"
	@echo "  python dump-enis.py --vpc-id vpc-12345678 > enis.json"
	@echo "  python dump-enis.py --vpc-id vpc-12345678 | jq '.NetworkInterfaces[].NetworkInterfaceId'"

install:
	pip install -r requirements.txt

run:
	@if [ -z "$(VPC_ID)" ]; then \
		echo "Error: VPC_ID environment variable is required"; \
		echo "Usage: VPC_ID=vpc-12345678 make run"; \
		exit 1; \
	fi
	python dump-enis.py --vpc-id $(VPC_ID) > enis.json

clean:
	rm -f enis.json *.json
	rm -rf __pycache__/
	rm -f *.pyc
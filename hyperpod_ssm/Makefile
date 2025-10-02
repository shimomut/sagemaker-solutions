# HyperPod SSM Interactive Shell Makefile

.PHONY: help install run clean test

help:
	@echo "Available targets:"
	@echo "  install    - Install Python dependencies"
	@echo "  run        - Run the SSM shell interactively"
	@echo "  test       - Test SSM connectivity"
	@echo "  clean      - Clean up temporary files"
	@echo ""
	@echo "Usage examples:"
	@echo "  make run"
	@echo "  make run CLUSTER=my-cluster"
	@echo "  make run CLUSTER=my-cluster GROUP=worker-group"
	@echo "  make run CLUSTER=my-cluster INSTANCE=i-1234567890abcdef0"
	@echo "  make test CLUSTER=my-cluster"

install:
	pip install -r requirements.txt

run:
ifdef INSTANCE
	python hyperpod_ssm.py --cluster $(CLUSTER) --instance-id $(INSTANCE) $(if $(DEBUG),--debug)
else ifdef GROUP
	python hyperpod_ssm.py --cluster $(CLUSTER) --instance-group $(GROUP) $(if $(DEBUG),--debug)
else ifdef CLUSTER
	python hyperpod_ssm.py --cluster $(CLUSTER) $(if $(DEBUG),--debug)
else
	python hyperpod_ssm.py $(if $(DEBUG),--debug)
endif

list-clusters:
	python hyperpod_ssm.py --list-clusters

list-nodes:
ifndef CLUSTER
	@echo "Error: CLUSTER parameter is required"
	@echo "Usage: make list-nodes CLUSTER=my-cluster"
	@exit 1
endif
	python hyperpod_ssm.py --cluster $(CLUSTER) --list-nodes

test:
ifndef CLUSTER
	@echo "Error: CLUSTER parameter is required"
	@echo "Usage: make test CLUSTER=my-cluster"
	@exit 1
endif
	@echo "Testing SSM connectivity to cluster $(CLUSTER)..."
	python hyperpod_ssm.py --cluster $(CLUSTER) --debug

clean:
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -delete
	find . -type f -name ".DS_Store" -delete

# Development targets
debug:
	$(MAKE) run DEBUG=1

# Quick access targets
connect:
ifndef CLUSTER
	@echo "Error: CLUSTER parameter is required"
	@echo "Usage: make connect CLUSTER=my-cluster [GROUP=group-name] [INSTANCE=instance-id]"
	@exit 1
endif
	$(MAKE) run CLUSTER=$(CLUSTER) $(if $(GROUP),GROUP=$(GROUP)) $(if $(INSTANCE),INSTANCE=$(INSTANCE))
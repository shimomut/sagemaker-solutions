# HyperPod x AWS DevOps Agent — experiment scaffolding
#
# Right now this directory only hosts the AWS DevOps Agent PDF docs and a
# helper to extract them to .txt for searching. We'll grow it as the
# experiment takes shape.

PYTHON3 ?= python3

VENV_DIR    := .venv
VENV_PYTHON := $(VENV_DIR)/bin/python
VENV_PIP    := $(VENV_DIR)/bin/pip
VENV_STAMP  := $(VENV_DIR)/.installed

DOCS_DIR := docs
PDFS     := $(wildcard $(DOCS_DIR)/*.pdf)
TXTS     := $(PDFS:.pdf=.txt)

.PHONY: help venv extract-docs clean

help:
	@echo "Available targets:"
	@echo "  venv         - Create local virtualenv ($(VENV_DIR)) using $(PYTHON3) and install deps"
	@echo "  extract-docs - Extract every PDF under $(DOCS_DIR)/ to a sibling .txt file"
	@echo "  clean        - Remove the virtualenv and extracted .txt files"

venv: $(VENV_STAMP)

$(VENV_STAMP): requirements.txt
	@if [ ! -x "$(VENV_PYTHON)" ]; then \
		echo "Creating venv at $(VENV_DIR) using $(PYTHON3)..."; \
		$(PYTHON3) -m venv $(VENV_DIR); \
	fi
	$(VENV_PIP) install --upgrade pip
	$(VENV_PIP) install -r requirements.txt
	@touch $(VENV_STAMP)

extract-docs: venv
	@if [ -z "$(PDFS)" ]; then \
		echo "No PDFs found under $(DOCS_DIR)/"; \
		exit 0; \
	fi
	$(VENV_PYTHON) extract_pdf.py $(PDFS)

clean:
	rm -rf $(VENV_DIR)
	rm -f $(TXTS)

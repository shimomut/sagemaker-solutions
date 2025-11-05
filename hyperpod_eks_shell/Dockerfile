FROM ubuntu:22.04

# Set environment variables
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

# Update package list and install basic tools
RUN apt-get update && apt-get install -y \
    curl \
    wget \
    vim \
    git \
    unzip \
    jq \
    htop \
    tree \
    ca-certificates \
    gnupg \
    lsb-release \
    && rm -rf /var/lib/apt/lists/*

# Install Python 3.11 and pip
RUN apt-get update && apt-get install -y \
    python3.11 \
    python3.11-dev \
    python3.11-venv \
    python3-pip \
    && rm -rf /var/lib/apt/lists/*

# Create symlinks for python and pip
RUN ln -sf /usr/bin/python3.11 /usr/bin/python && \
    ln -sf /usr/bin/python3.11 /usr/bin/python3

# Upgrade pip
RUN python -m pip install --upgrade pip

# Install AWS CLI v2
RUN curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip" && \
    unzip awscliv2.zip && \
    ./aws/install && \
    rm -rf awscliv2.zip aws/

# Install common Python packages for debugging and development
RUN pip install \
    boto3 \
    requests \
    ipython

# Create workspace directory
RUN mkdir -p /workspace

# Set working directory
WORKDIR /workspace

# Default command to keep container running
CMD ["sleep", "infinity"]
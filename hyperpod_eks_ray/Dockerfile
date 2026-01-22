# Base Ray image with GPU support
FROM rayproject/ray:2.42.1-py310-gpu

# Install additional dependencies for training
RUN pip install --no-cache-dir \
    torch==2.1.0 \
    torchvision==0.16.0 \
    transformers==4.35.0 \
    datasets==2.14.0 \
    accelerate==0.24.0 \
    deepspeed==0.12.0 \
    wandb==0.16.0

# Set working directory
WORKDIR /app

# Copy training scripts (if any)
# COPY . /app/

# Set environment variables
ENV RAY_DEDUP_LOGS=0

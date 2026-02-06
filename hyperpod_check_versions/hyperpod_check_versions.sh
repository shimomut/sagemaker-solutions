#!/bin/bash
# Script to investigate software component versions on HyperPod EKS cluster instances
# This helps determine appropriate versions for GDRCOPY, EFA, AWS OFI NCCL, NCCL, etc.

set -e

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Output file
OUTPUT_FILE="component_versions_$(hostname)_$(date +%Y%m%d_%H%M%S).txt"

echo "========================================" | tee -a "$OUTPUT_FILE"
echo "Software Component Version Investigation" | tee -a "$OUTPUT_FILE"
echo "Host: $(hostname)" | tee -a "$OUTPUT_FILE"
echo "Date: $(date)" | tee -a "$OUTPUT_FILE"
echo "========================================" | tee -a "$OUTPUT_FILE"
echo "" | tee -a "$OUTPUT_FILE"

# Function to print section headers
print_section() {
    echo -e "${BLUE}========================================${NC}" | tee -a "$OUTPUT_FILE"
    echo -e "${BLUE}$1${NC}" | tee -a "$OUTPUT_FILE"
    echo -e "${BLUE}========================================${NC}" | tee -a "$OUTPUT_FILE"
}

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# System Information
print_section "System Information"
echo "OS: $(cat /etc/os-release | grep PRETTY_NAME | cut -d'"' -f2)" | tee -a "$OUTPUT_FILE"
echo "Kernel: $(uname -r)" | tee -a "$OUTPUT_FILE"
echo "Architecture: $(uname -m)" | tee -a "$OUTPUT_FILE"
echo "" | tee -a "$OUTPUT_FILE"

# CUDA Version
print_section "CUDA Information"

if command_exists nvidia-smi; then
    echo "NVIDIA Driver Information:" | tee -a "$OUTPUT_FILE"
    DRIVER_VERSION=$(nvidia-smi --query-gpu=driver_version --format=csv,noheader | head -1)
    echo "NVIDIA GPU Driver Version: $DRIVER_VERSION" | tee -a "$OUTPUT_FILE"
    
    # Get max supported CUDA version from nvidia-smi
    MAX_CUDA_VERSION=$(nvidia-smi | grep "CUDA Version" | sed -n 's/.*CUDA Version: \([0-9.]*\).*/\1/p' | head -1)
    if [ -n "$MAX_CUDA_VERSION" ]; then
        echo "Max Supported CUDA Version: $MAX_CUDA_VERSION (from driver)" | tee -a "$OUTPUT_FILE"
        echo -e "${GREEN}Note: This is the maximum CUDA version supported by the driver, not the installed toolkit version.${NC}" | tee -a "$OUTPUT_FILE"
    fi
    echo "" | tee -a "$OUTPUT_FILE"
    
    echo "GPU Information:" | tee -a "$OUTPUT_FILE"
    nvidia-smi -L | tee -a "$OUTPUT_FILE"
    echo "" | tee -a "$OUTPUT_FILE"
else
    echo -e "${YELLOW}nvidia-smi not found${NC}" | tee -a "$OUTPUT_FILE"
fi

if command_exists nvcc; then
    echo "CUDA Toolkit (nvcc):" | tee -a "$OUTPUT_FILE"
    nvcc --version | tee -a "$OUTPUT_FILE"
    NVCC_VERSION=$(nvcc --version | grep "release" | sed -n 's/.*release \([0-9.]*\).*/\1/p')
    if [ -n "$NVCC_VERSION" ]; then
        echo "CUDA Toolkit Version: $NVCC_VERSION (installed)" | tee -a "$OUTPUT_FILE"
    fi
    echo "" | tee -a "$OUTPUT_FILE"
else
    echo -e "${YELLOW}nvcc not found${NC}" | tee -a "$OUTPUT_FILE"
fi

# Check for installed CUDA toolkit directories
echo "Installed CUDA Toolkits:" | tee -a "$OUTPUT_FILE"
if [ -d /usr/local ]; then
    CUDA_DIRS=$(ls -d /usr/local/cuda-* 2>/dev/null)
    if [ -n "$CUDA_DIRS" ]; then
        echo "$CUDA_DIRS" | tee -a "$OUTPUT_FILE"
        # Check symlink
        if [ -L /usr/local/cuda ]; then
            CUDA_LINK=$(readlink /usr/local/cuda)
            echo "Active CUDA (symlink): /usr/local/cuda -> $CUDA_LINK" | tee -a "$OUTPUT_FILE"
        fi
    else
        echo "No CUDA toolkit directories found in /usr/local" | tee -a "$OUTPUT_FILE"
    fi
else
    echo "/usr/local not found" | tee -a "$OUTPUT_FILE"
fi

if [ -f /usr/local/cuda/version.txt ]; then
    echo "" | tee -a "$OUTPUT_FILE"
    echo "CUDA Version File:" | tee -a "$OUTPUT_FILE"
    cat /usr/local/cuda/version.txt | tee -a "$OUTPUT_FILE"
fi
echo "" | tee -a "$OUTPUT_FILE"

# NCCL Version
print_section "NCCL Information"

# Find NCCL libraries and extract version from filename
echo "NCCL Libraries:" | tee -a "$OUTPUT_FILE"
NCCL_LIBS=$(find /usr/local/cuda* /usr/lib* /usr/local/lib* /opt/nccl -name "libnccl.so*" 2>/dev/null | head -20)
if [ -n "$NCCL_LIBS" ]; then
    echo "$NCCL_LIBS" | tee -a "$OUTPUT_FILE"
    echo "" | tee -a "$OUTPUT_FILE"
    
    # Extract version from library filename (e.g., libnccl.so.2.26.5 -> 2.26.5)
    for lib in $NCCL_LIBS; do
        if [[ $lib =~ libnccl\.so\.([0-9]+\.[0-9]+\.[0-9]+) ]]; then
            NCCL_LIB_VERSION="${BASH_REMATCH[1]}"
            echo "NCCL version from library: v${NCCL_LIB_VERSION}" | tee -a "$OUTPUT_FILE"
            break
        fi
    done
    echo "" | tee -a "$OUTPUT_FILE"
else
    echo "No NCCL libraries found" | tee -a "$OUTPUT_FILE"
    echo "" | tee -a "$OUTPUT_FILE"
fi

# Check for NCCL header files
echo "Searching for NCCL header files:" | tee -a "$OUTPUT_FILE"
NCCL_HEADERS=$(find /usr/local/cuda*/include /usr/include /usr/local/include /opt/nccl -name "nccl.h" 2>/dev/null | head -5)
if [ -n "$NCCL_HEADERS" ]; then
    echo "$NCCL_HEADERS" | tee -a "$OUTPUT_FILE"
    echo "" | tee -a "$OUTPUT_FILE"
    
    # Try to extract version from first header
    for nccl_header in $NCCL_HEADERS; do
        echo "NCCL version from $nccl_header:" | tee -a "$OUTPUT_FILE"
        grep -E "NCCL_MAJOR|NCCL_MINOR|NCCL_PATCH" "$nccl_header" 2>/dev/null | head -3 | tee -a "$OUTPUT_FILE"
        echo "" | tee -a "$OUTPUT_FILE"
        break
    done
else
    echo "No NCCL headers found" | tee -a "$OUTPUT_FILE"
    echo "" | tee -a "$OUTPUT_FILE"
fi

# Check package manager for NCCL
if command_exists dpkg; then
    echo "NCCL packages (dpkg):" | tee -a "$OUTPUT_FILE"
    dpkg -l | grep -i nccl | tee -a "$OUTPUT_FILE"
    echo "" | tee -a "$OUTPUT_FILE"
fi

if command_exists rpm; then
    echo "NCCL packages (rpm):" | tee -a "$OUTPUT_FILE"
    rpm -qa | grep -i nccl | tee -a "$OUTPUT_FILE"
    echo "" | tee -a "$OUTPUT_FILE"
fi
echo "" | tee -a "$OUTPUT_FILE"

# EFA (Elastic Fabric Adapter) Information
print_section "EFA Information"

# Check EFA installed packages file (most reliable source)
if [ -f /opt/amazon/efa_installed_packages ]; then
    echo "EFA Installed Packages File:" | tee -a "$OUTPUT_FILE"
    cat /opt/amazon/efa_installed_packages | tee -a "$OUTPUT_FILE"
    echo "" | tee -a "$OUTPUT_FILE"
fi

if command_exists fi_info; then
    echo "Libfabric version:" | tee -a "$OUTPUT_FILE"
    fi_info --version 2>&1 | tee -a "$OUTPUT_FILE"
    echo "" | tee -a "$OUTPUT_FILE"
    
    echo "EFA Provider information:" | tee -a "$OUTPUT_FILE"
    fi_info -p efa 2>&1 | head -50 | tee -a "$OUTPUT_FILE"
    echo "" | tee -a "$OUTPUT_FILE"
else
    echo -e "${YELLOW}fi_info not found${NC}" | tee -a "$OUTPUT_FILE"
fi

# Check EFA installer version
if [ -f /opt/amazon/efa/bin/fi_info ]; then
    echo "EFA installation found at /opt/amazon/efa/" | tee -a "$OUTPUT_FILE"
    /opt/amazon/efa/bin/fi_info --version 2>&1 | tee -a "$OUTPUT_FILE"
    echo "" | tee -a "$OUTPUT_FILE"
fi

# Check for EFA packages
if command_exists dpkg; then
    echo "EFA packages (dpkg):" | tee -a "$OUTPUT_FILE"
    dpkg -l | grep -E "efa|libfabric" | tee -a "$OUTPUT_FILE"
    echo "" | tee -a "$OUTPUT_FILE"
fi

if command_exists rpm; then
    echo "EFA packages (rpm):" | tee -a "$OUTPUT_FILE"
    rpm -qa | grep -E "efa|libfabric" | tee -a "$OUTPUT_FILE"
    echo "" | tee -a "$OUTPUT_FILE"
fi

# Check EFA device
echo "EFA Network Devices:" | tee -a "$OUTPUT_FILE"
if [ -d /sys/class/infiniband ]; then
    ls -la /sys/class/infiniband/ | tee -a "$OUTPUT_FILE"
    echo "" | tee -a "$OUTPUT_FILE"
else
    echo -e "${YELLOW}No InfiniBand devices found${NC}" | tee -a "$OUTPUT_FILE"
fi
echo "" | tee -a "$OUTPUT_FILE"

# AWS OFI NCCL Plugin
print_section "AWS OFI NCCL Plugin Information"

# Check EFA installed packages file for libnccl-ofi version
if [ -f /opt/amazon/efa_installed_packages ]; then
    echo "AWS OFI NCCL version from EFA installed packages:" | tee -a "$OUTPUT_FILE"
    grep "libnccl-ofi" /opt/amazon/efa_installed_packages | tee -a "$OUTPUT_FILE"
    echo "" | tee -a "$OUTPUT_FILE"
fi

echo "Searching for AWS OFI NCCL libraries:" | tee -a "$OUTPUT_FILE"
find /usr/lib* /opt/amazon -name "*ofi*nccl*" -o -name "*aws-ofi-nccl*" 2>/dev/null | head -10 | tee -a "$OUTPUT_FILE"
echo "" | tee -a "$OUTPUT_FILE"

if command_exists dpkg; then
    echo "AWS OFI NCCL packages (dpkg):" | tee -a "$OUTPUT_FILE"
    dpkg -l | grep -i "ofi.*nccl\|aws.*ofi\|libnccl-ofi" | tee -a "$OUTPUT_FILE"
    echo "" | tee -a "$OUTPUT_FILE"
fi

if command_exists rpm; then
    echo "AWS OFI NCCL packages (rpm):" | tee -a "$OUTPUT_FILE"
    rpm -qa | grep -i "ofi.*nccl\|aws.*ofi\|libnccl-ofi" | tee -a "$OUTPUT_FILE"
    echo "" | tee -a "$OUTPUT_FILE"
fi

# Check for plugin library
if [ -f /opt/amazon/ofi-nccl/lib/libnccl-net.so ]; then
    echo "AWS OFI NCCL plugin found at /opt/amazon/ofi-nccl/" | tee -a "$OUTPUT_FILE"
    ls -lh /opt/amazon/ofi-nccl/lib/ | tee -a "$OUTPUT_FILE"
    echo "" | tee -a "$OUTPUT_FILE"
fi
echo "" | tee -a "$OUTPUT_FILE"

# GDRCopy Information
print_section "GDRCopy Information"

# Check for GDRCopy packages (most reliable)
if command_exists rpm; then
    echo "GDRCopy packages (rpm):" | tee -a "$OUTPUT_FILE"
    rpm -qa | grep -i gdrcopy | tee -a "$OUTPUT_FILE"
    echo "" | tee -a "$OUTPUT_FILE"
fi

if command_exists dpkg; then
    echo "GDRCopy packages (dpkg):" | tee -a "$OUTPUT_FILE"
    dpkg -l | grep -i gdrcopy | tee -a "$OUTPUT_FILE"
    echo "" | tee -a "$OUTPUT_FILE"
fi

# Check for GDRCopy libraries
echo "GDRCopy libraries:" | tee -a "$OUTPUT_FILE"
find /usr/lib* /usr/local/lib* /opt/gdrcopy -name "*gdrcopy*" -o -name "libgdrapi.so*" 2>/dev/null | head -10 | tee -a "$OUTPUT_FILE"
echo "" | tee -a "$OUTPUT_FILE"

# Check kernel module
echo "GDRCopy kernel module:" | tee -a "$OUTPUT_FILE"
lsmod | grep gdrdrv | tee -a "$OUTPUT_FILE"
if [ $? -ne 0 ]; then
    echo -e "${YELLOW}GDRCopy kernel module not loaded${NC}" | tee -a "$OUTPUT_FILE"
fi
echo "" | tee -a "$OUTPUT_FILE"

# MPI Information
print_section "MPI Information"
if command_exists mpirun; then
    echo "MPI version:" | tee -a "$OUTPUT_FILE"
    mpirun --version 2>&1 | tee -a "$OUTPUT_FILE"
    echo "" | tee -a "$OUTPUT_FILE"
fi

if [ -d /opt/amazon/openmpi ]; then
    echo "OpenMPI installation found at /opt/amazon/openmpi/" | tee -a "$OUTPUT_FILE"
    if [ -f /opt/amazon/openmpi/bin/mpirun ]; then
        /opt/amazon/openmpi/bin/mpirun --version 2>&1 | tee -a "$OUTPUT_FILE"
    fi
    echo "" | tee -a "$OUTPUT_FILE"
fi

if command_exists dpkg; then
    echo "MPI packages (dpkg):" | tee -a "$OUTPUT_FILE"
    dpkg -l | grep -E "openmpi|mpich" | tee -a "$OUTPUT_FILE"
    echo "" | tee -a "$OUTPUT_FILE"
fi
echo "" | tee -a "$OUTPUT_FILE"

# Python and PyTorch Information
print_section "Python and ML Framework Information"
if command_exists python3; then
    echo "Python version:" | tee -a "$OUTPUT_FILE"
    python3 --version | tee -a "$OUTPUT_FILE"
    echo "" | tee -a "$OUTPUT_FILE"
    
    echo "Checking PyTorch installation:" | tee -a "$OUTPUT_FILE"
    python3 -c "import torch; print(f'PyTorch version: {torch.__version__}'); print(f'CUDA available: {torch.cuda.is_available()}'); print(f'CUDA version: {torch.version.cuda if torch.cuda.is_available() else \"N/A\"}')" 2>&1 | tee -a "$OUTPUT_FILE"
    echo "" | tee -a "$OUTPUT_FILE"
fi
echo "" | tee -a "$OUTPUT_FILE"

# Environment Variables
print_section "Relevant Environment Variables"
echo "LD_LIBRARY_PATH:" | tee -a "$OUTPUT_FILE"
echo "$LD_LIBRARY_PATH" | tee -a "$OUTPUT_FILE"
echo "" | tee -a "$OUTPUT_FILE"

echo "PATH:" | tee -a "$OUTPUT_FILE"
echo "$PATH" | tee -a "$OUTPUT_FILE"
echo "" | tee -a "$OUTPUT_FILE"

echo "NCCL related variables:" | tee -a "$OUTPUT_FILE"
env | grep -i nccl | tee -a "$OUTPUT_FILE"
echo "" | tee -a "$OUTPUT_FILE"

echo "EFA related variables:" | tee -a "$OUTPUT_FILE"
env | grep -i efa | tee -a "$OUTPUT_FILE"
echo "" | tee -a "$OUTPUT_FILE"

# Docker Information (if available)
print_section "Container Runtime Information"
if command_exists docker; then
    echo "Docker version:" | tee -a "$OUTPUT_FILE"
    docker --version 2>&1 | tee -a "$OUTPUT_FILE"
    echo "" | tee -a "$OUTPUT_FILE"
fi

if command_exists kubectl; then
    echo "Kubernetes client version:" | tee -a "$OUTPUT_FILE"
    kubectl version --client 2>&1 | tee -a "$OUTPUT_FILE"
    echo "" | tee -a "$OUTPUT_FILE"
fi
echo "" | tee -a "$OUTPUT_FILE"

# Summary Section
print_section "Version Summary"
echo "Based on the investigation above, here are the detected versions:" | tee -a "$OUTPUT_FILE"
echo "" | tee -a "$OUTPUT_FILE"

# Try to extract key versions
echo "Key Component Versions:" | tee -a "$OUTPUT_FILE"
echo "----------------------" | tee -a "$OUTPUT_FILE"

# Driver and CUDA
if command_exists nvidia-smi; then
    DRIVER_VER=$(nvidia-smi --query-gpu=driver_version --format=csv,noheader | head -1)
    echo "NVIDIA_GPU_DRIVER_VERSION: ${DRIVER_VER:-Unknown}" | tee -a "$OUTPUT_FILE"
    
    MAX_CUDA=$(nvidia-smi | grep "CUDA Version" | sed -n 's/.*CUDA Version: \([0-9.]*\).*/\1/p' | head -1)
    if [ -n "$MAX_CUDA" ]; then
        echo "MAX_SUPPORTED_CUDA_VERSION: ${MAX_CUDA} (from driver)" | tee -a "$OUTPUT_FILE"
    fi
fi

# Installed CUDA Toolkit
if command_exists nvcc; then
    CUDA_VER=$(nvcc --version | grep "release" | sed -n 's/.*release \([0-9.]*\).*/\1/p')
    echo "CUDA_TOOLKIT_VERSION: ${CUDA_VER:-Unknown} (installed)" | tee -a "$OUTPUT_FILE"
elif [ -L /usr/local/cuda ]; then
    CUDA_LINK=$(readlink /usr/local/cuda)
    CUDA_VER=$(echo "$CUDA_LINK" | sed -n 's/.*cuda-\([0-9.]*\).*/\1/p')
    if [ -n "$CUDA_VER" ]; then
        echo "CUDA_TOOLKIT_VERSION: ${CUDA_VER} (from symlink)" | tee -a "$OUTPUT_FILE"
    fi
fi

# NCCL
# First try to get version from library filename
NCCL_LIBS=$(find /usr/local/cuda* /usr/lib* /usr/local/lib* /opt/nccl -name "libnccl.so*" 2>/dev/null | head -20)
if [ -n "$NCCL_LIBS" ]; then
    for lib in $NCCL_LIBS; do
        if [[ $lib =~ libnccl\.so\.([0-9]+\.[0-9]+\.[0-9]+) ]]; then
            NCCL_LIB_VERSION="${BASH_REMATCH[1]}"
            echo "NCCL_VERSION: v${NCCL_LIB_VERSION}-1" | tee -a "$OUTPUT_FILE"
            break
        fi
    done
fi

# Fallback to header file if library version not found
if [ -z "$NCCL_LIB_VERSION" ]; then
    NCCL_HEADER=$(find /usr/local/cuda*/include /usr/include /usr/local/include /opt/nccl -name "nccl.h" 2>/dev/null | head -1)
    if [ -n "$NCCL_HEADER" ]; then
        NCCL_MAJOR=$(grep "NCCL_MAJOR" "$NCCL_HEADER" | head -1 | awk '{print $3}')
        NCCL_MINOR=$(grep "NCCL_MINOR" "$NCCL_HEADER" | head -1 | awk '{print $3}')
        NCCL_PATCH=$(grep "NCCL_PATCH" "$NCCL_HEADER" | head -1 | awk '{print $3}')
        if [ -n "$NCCL_MAJOR" ] && [ -n "$NCCL_MINOR" ] && [ -n "$NCCL_PATCH" ]; then
            echo "NCCL_VERSION: v${NCCL_MAJOR}.${NCCL_MINOR}.${NCCL_PATCH}-1 (from header)" | tee -a "$OUTPUT_FILE"
        fi
    fi
fi

# EFA
if [ -f /opt/amazon/efa_installed_packages ]; then
    EFA_INSTALLER_VER=$(grep "# EFA installer version:" /opt/amazon/efa_installed_packages | sed -n 's/.*version: \([0-9.]*\).*/\1/p')
    echo "EFA_INSTALLER_VERSION: ${EFA_INSTALLER_VER:-Unknown}" | tee -a "$OUTPUT_FILE"
    
    # Extract libfabric version
    LIBFABRIC_VER=$(grep "libfabric-aws-" /opt/amazon/efa_installed_packages | sed -n 's/.*libfabric-aws-\([0-9.]*\)amzn.*/\1/p' | head -1)
    if [ -n "$LIBFABRIC_VER" ]; then
        echo "LIBFABRIC_VERSION: ${LIBFABRIC_VER}" | tee -a "$OUTPUT_FILE"
    fi
elif command_exists fi_info; then
    EFA_VER=$(fi_info --version 2>&1 | grep "libfabric" | sed -n 's/.*libfabric: \([0-9.]*\).*/\1/p' | head -1)
    echo "EFA_INSTALLER_VERSION: ${EFA_VER:-Unknown} (libfabric version, check for exact installer version)" | tee -a "$OUTPUT_FILE"
fi

# AWS OFI NCCL
if [ -f /opt/amazon/efa_installed_packages ]; then
    AWS_OFI_NCCL_VER=$(grep "libnccl-ofi-" /opt/amazon/efa_installed_packages | sed -n 's/.*libnccl-ofi-\([0-9.]*\)-.*/\1/p' | head -1)
    if [ -n "$AWS_OFI_NCCL_VER" ]; then
        echo "AWS_OFI_NCCL_VERSION: v${AWS_OFI_NCCL_VER}" | tee -a "$OUTPUT_FILE"
    fi
else
    OFI_NCCL_LIB=$(find /opt/amazon/ofi-nccl -name "libnccl-net.so" 2>/dev/null | head -1)
    if [ -n "$OFI_NCCL_LIB" ]; then
        echo "AWS_OFI_NCCL_VERSION: Found at $OFI_NCCL_LIB (check package manager for version)" | tee -a "$OUTPUT_FILE"
    fi
fi

# GDRCopy
if command_exists rpm; then
    GDRCOPY_VER=$(rpm -qa | grep "^gdrcopy-[0-9]" | head -1 | sed -n 's/gdrcopy-\([0-9.]*\)-.*/\1/p')
    if [ -n "$GDRCOPY_VER" ]; then
        echo "GDRCOPY_VERSION: v${GDRCOPY_VER}" | tee -a "$OUTPUT_FILE"
    fi
elif command_exists dpkg; then
    GDRCOPY_VER=$(dpkg -l | grep "^ii.*gdrcopy" | head -1 | awk '{print $3}' | sed -n 's/\([0-9.]*\)-.*/\1/p')
    if [ -n "$GDRCOPY_VER" ]; then
        echo "GDRCOPY_VERSION: v${GDRCOPY_VER}" | tee -a "$OUTPUT_FILE"
    fi
else
    GDRCOPY_LIB=$(find /usr /opt -name "libgdrapi.so*" 2>/dev/null | head -1)
    if [ -n "$GDRCOPY_LIB" ]; then
        echo "GDRCOPY_VERSION: Found at $GDRCOPY_LIB (check package manager for version)" | tee -a "$OUTPUT_FILE"
    fi
fi

echo "" | tee -a "$OUTPUT_FILE"
echo "========================================" | tee -a "$OUTPUT_FILE"
echo -e "${BLUE}CUDA/Driver Compatibility Analysis${NC}" | tee -a "$OUTPUT_FILE"
echo "========================================" | tee -a "$OUTPUT_FILE"

# Analyze CUDA compatibility
if [ -n "$DRIVER_VER" ] && [ -n "$MAX_CUDA" ]; then
    echo "NVIDIA GPU Driver Version: $DRIVER_VER" | tee -a "$OUTPUT_FILE"
    echo "Max Supported CUDA Version: $MAX_CUDA" | tee -a "$OUTPUT_FILE"
    echo "" | tee -a "$OUTPUT_FILE"
    
    # Determine driver series
    DRIVER_MAJOR=$(echo "$DRIVER_VER" | cut -d'.' -f1)
    
    if [ "$DRIVER_MAJOR" -ge 580 ]; then
        echo -e "${GREEN}✓ Driver supports CUDA 13.x, 12.x, and 11.x${NC}" | tee -a "$OUTPUT_FILE"
        echo "  Compatible with containers using CUDA 11.0 - 13.0" | tee -a "$OUTPUT_FILE"
    elif [ "$DRIVER_MAJOR" -ge 570 ]; then
        echo -e "${GREEN}✓ Driver supports CUDA 12.8+ (Blackwell), 12.x, and 11.x${NC}" | tee -a "$OUTPUT_FILE"
        echo "  Compatible with containers using CUDA 11.0 - 12.9" | tee -a "$OUTPUT_FILE"
    elif [ "$DRIVER_MAJOR" -ge 525 ]; then
        echo -e "${GREEN}✓ Driver supports CUDA 12.0-12.7 and 11.x${NC}" | tee -a "$OUTPUT_FILE"
        echo "  Compatible with containers using CUDA 11.0 - 12.7" | tee -a "$OUTPUT_FILE"
        echo -e "${YELLOW}  ⚠ NOT compatible with CUDA 12.8+ (requires driver 570+)${NC}" | tee -a "$OUTPUT_FILE"
    elif [ "$DRIVER_MAJOR" -ge 450 ]; then
        echo -e "${GREEN}✓ Driver supports CUDA 11.x${NC}" | tee -a "$OUTPUT_FILE"
        echo "  Compatible with containers using CUDA 11.0 - 11.8" | tee -a "$OUTPUT_FILE"
        echo -e "${YELLOW}  ⚠ NOT compatible with CUDA 12.x (requires driver 525+)${NC}" | tee -a "$OUTPUT_FILE"
    else
        echo -e "${YELLOW}⚠ Driver version is older than CUDA 11.x baseline${NC}" | tee -a "$OUTPUT_FILE"
    fi
    
    echo "" | tee -a "$OUTPUT_FILE"
    echo "Note: The 'CUDA Version' shown in nvidia-smi is the MAX supported version," | tee -a "$OUTPUT_FILE"
    echo "      not the installed toolkit version. Containers can use any CUDA version" | tee -a "$OUTPUT_FILE"
    echo "      up to this maximum." | tee -a "$OUTPUT_FILE"
fi

echo "" | tee -a "$OUTPUT_FILE"
echo "========================================" | tee -a "$OUTPUT_FILE"
echo -e "${GREEN}Investigation complete!${NC}" | tee -a "$OUTPUT_FILE"
echo "Results saved to: $OUTPUT_FILE" | tee -a "$OUTPUT_FILE"
echo "========================================" | tee -a "$OUTPUT_FILE"

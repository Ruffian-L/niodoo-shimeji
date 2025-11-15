#!/bin/bash

# Build script for Niodoo Shimeji AI Desktop Companion

set -e

echo "==================================="
echo "Building Niodoo Shimeji Companion"
echo "==================================="

# Check if build directory exists
if [ ! -d "build" ]; then
    echo "Creating build directory..."
    mkdir -p build
fi

cd build

# Run CMake
echo "Running CMake..."
cmake ..

# Build the project
echo "Building..."
make -j$(nproc) ShimejiCompanion

# Check if build was successful
if [ -f "ShimejiCompanion" ]; then
    echo ""
    echo "==================================="
    echo "Build successful!"
    echo "==================================="
    echo ""
    echo "To run the Shimeji companion:"
    echo "  cd build && ./ShimejiCompanion"
    echo ""
    echo "Make sure niodoo_real_integrated is running with:"
    echo "  NIODOO_TELEMETRY_ENABLED=true NIODOO_TELEMETRY_PORT=9999"
    echo ""
else
    echo ""
    echo "==================================="
    echo "Build failed!"
    echo "==================================="
    exit 1
fi


#!/bin/bash

# Brain Integration Build and Test Script
echo "🧠 Building Brain Integration System..."
echo "====================================="

# Create build directory
mkdir -p build
cd build

# Configure with CMake
echo "🔧 Configuring with CMake..."
cmake .. -DCMAKE_BUILD_TYPE=Release

if [ $? -ne 0 ]; then
    echo "❌ CMake configuration failed!"
    echo "   This might be due to missing dependencies."
    echo "   Try: sudo apt install libonnxruntime-dev"
    exit 1
fi

# Build the project
echo "🔨 Building project..."
make -j$(nproc)

if [ $? -ne 0 ]; then
    echo "❌ Build failed!"
    exit 1
fi

echo "✅ Build completed successfully!"
echo ""
echo "🎯 Ready to run:"
echo "   cd build"
echo "   ./BrainIntegration"
echo ""
echo "Or install system-wide:"
echo "   sudo make install"
echo "   brain-integration"

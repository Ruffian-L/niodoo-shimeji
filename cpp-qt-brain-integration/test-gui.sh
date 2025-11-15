#!/bin/bash

# Brain Integration GUI Test Script
echo "🧠 Testing Brain Integration GUI..."
echo "==================================="

# Check if build exists
if [ ! -d "build" ]; then
    echo "❌ Build directory not found!"
    echo "   Run test-build.sh first"
    exit 1
fi

cd build

# Check if executable exists
if [ ! -f "BrainIntegration" ]; then
    echo "❌ BrainIntegration executable not found!"
    echo "   Build failed or not completed"
    exit 1
fi

echo "🚀 Starting Brain Integration GUI..."
echo "==================================="

# Set environment variables for Qt
export QT_QPA_PLATFORM=xcb
export QT_LOGGING_RULES="*.debug=false"

# Run the application
./BrainIntegration

echo ""
echo "✅ GUI test completed"
echo "   Check the application window for the brain system interface"

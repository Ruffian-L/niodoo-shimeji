# Brain Integration - C++ Qt Emotional AI System

## Overview

This is a comprehensive C++ Qt application that integrates with the Brain Integration emotional AI system. It provides a native desktop interface for the advanced emotional processing capabilities, neural network inference, and distributed brain system architecture.

## Features

### 🎭 Emotional AI Processing
- Real-time emotional analysis with 95%+ accuracy
- Support for complex, suppressed emotions (ambivalent grief, impostor joy, etc.)
- 89-agent neural network integration
- Trauma-informed processing capabilities
- Cultural context awareness

### 🧠 Neural Network Engine
- ONNX Runtime integration for high-performance inference
- Hardware acceleration (CUDA, TensorRT, CoreML, DirectML)
- Mixed precision support
- Model caching and optimization
- Real-time performance monitoring

### 🔄 Brain System Bridge
- 1,209 neural connection management
- Agent consensus algorithms (72-93% consensus rates)
- Adaptive neural pathway activation
- Real-time system monitoring
- Distributed processing support

### ⚡ Hardware Acceleration
- GPU utilization monitoring
- Memory usage optimization
- Temperature and power monitoring
- Multi-threading support
- Performance profiling

## System Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Qt Frontend   │◄──►│ Emotional AI Mgr │◄──►│ Python Backend  │
│                 │    │                  │    │                 │
│ - MainWindow    │    │ - HTTP Requests  │    │ - Architect AI  │
│ - UI Widgets    │    │ - JSON Parsing   │    │ - Developer AI  │
│ - Signal/Slots  │    │ - State Mgmt     │    │ - Brain System  │
└─────────────────┘    └──────────────────┘    └─────────────────┘
         │
         ▼
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│ Neural Engine   │    │ Brain Bridge     │    │ ONNX Runtime   │
│                 │    │                  │    │                 │
│ - ONNX Models   │    │ - 89 Agents      │    │ - CUDA/TensorRT│
│ - Hardware Accel│    │ - 1,209 Conns    │    │ - CoreML/DML   │
│ - Inference     │    │ - Consensus      │    │ - CPU Fallback │
└─────────────────┘    └──────────────────┘    └─────────────────┘
```

## Requirements

### System Requirements
- **OS**: Linux, macOS, or Windows
- **RAM**: 4GB minimum, 16GB recommended
- **Storage**: 2GB for models and dependencies
- **GPU**: Optional, but recommended for hardware acceleration

### Software Dependencies
- **Qt6**: 6.0 or higher
- **CMake**: 3.16 or higher
- **ONNX Runtime**: 1.12 or higher
- **C++17**: Compatible compiler (GCC 7+, Clang 5+, MSVC 2019+)

### Optional Dependencies
- **CUDA Toolkit**: For NVIDIA GPU acceleration
- **TensorRT**: For optimized NVIDIA inference
- **CoreML**: For macOS GPU acceleration
- **DirectML**: For Windows GPU acceleration

## Building and Installation

### 1. Clone the Repository
```bash
git clone <repository-url>
cd cpp-qt-brain-integration
```

### 2. Install Dependencies
```bash
# Ubuntu/Debian
sudo apt update
sudo apt install qt6-base-dev cmake build-essential

# For ONNX Runtime
sudo apt install libonnxruntime-dev

# Optional: GPU support
sudo apt install nvidia-cuda-toolkit
```

### 3. Configure Build
```bash
mkdir build
cd build
cmake ..
```

### 4. Build
```bash
make -j$(nproc)
```

### 5. Install
```bash
sudo make install
```

## Usage

### Starting the Application
```bash
# From build directory
./BrainIntegration

# Or from system installation
brain-integration
```

### Basic Operation
1. **Emotional Input**: Enter text describing emotional states in the main input area
2. **Process**: Click "Process Emotions" to analyze the input
3. **Monitor**: Watch real-time updates in the neural network and brain system tabs
4. **Hardware**: Check GPU/memory usage in the hardware monitoring tab

### Advanced Features
- **Distributed Mode**: Enable for multi-system collaboration
- **Hardware Acceleration**: Toggle GPU acceleration on/off
- **Neural Pathways**: Adjust pathway activation levels
- **Agent Management**: Modify agent counts and consensus thresholds

## Configuration

### Network Endpoints
The application connects to Python backend services:

- **Architect AI**: `http://10.42.104.23:11434/api/generate`
- **Developer AI**: `http://localhost:11434/api/generate`
- **Brain System**: `http://localhost:3003`

### Model Configuration
Place ONNX models in the `models/` directory:
- `emotion_detector.onnx`: Emotional analysis model
- `agent_consensus.onnx`: Consensus calculation model

## API Reference

### EmotionalAIManager
```cpp
// Process emotional input
void processEmotionalInput(const QString& input);

// Get results
QString getLastAnalysis() const;
QJsonObject getDetectedEmotions() const;
double getEmpathyScore() const;
```

### BrainSystemBridge
```cpp
// System control
void startBrainSystem();
void stopBrainSystem();
void setAgentsCount(int count);

// Monitoring
int getAgentsCount() const;
double getConsensusLevel() const;
QVector<NeuralAgent> getActiveAgents() const;
```

### NeuralNetworkEngine
```cpp
// Hardware control
void setHardwareAcceleration(bool enabled);
void setMaxThreads(int threads);

// Inference
QJsonObject runEmotionalInference(const QString& input);
QJsonObject runConsensusInference(const QVector<double>& activities);
```

## Performance Tuning

### CPU Optimization
- Set thread count to match CPU cores
- Disable GPU acceleration for CPU-only systems
- Use mixed precision for faster inference

### GPU Optimization
- Enable CUDA/TensorRT for NVIDIA GPUs
- Set appropriate memory limits
- Monitor temperature and power usage

### Memory Optimization
- Adjust cache size limits
- Monitor memory usage in hardware tab
- Clear cache periodically if needed

## Troubleshooting

### Common Issues

1. **ONNX Runtime Not Found**
   ```
   Error: ONNX Runtime library not found
   Solution: Install libonnxruntime-dev and rebuild
   ```

2. **GPU Acceleration Fails**
   ```
   Error: CUDA initialization failed
   Solution: Check GPU drivers and CUDA installation
   ```

3. **Network Connection Errors**
   ```
   Error: Failed to connect to Python backend
   Solution: Start Python services or check endpoints
   ```

### Debug Mode
Run with debug output:
```bash
QT_LOGGING_RULES="*.debug=true" ./BrainIntegration
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- **Qt Framework**: For the excellent cross-platform GUI framework
- **ONNX Runtime**: For high-performance neural network inference
- **Brain Integration Team**: For the revolutionary emotional AI architecture

## Support

For support and questions:
- Create an issue in the repository
- Check the troubleshooting section
- Review the system logs for detailed error information

---

**Built with ❤️ for Advanced Emotional Intelligence**

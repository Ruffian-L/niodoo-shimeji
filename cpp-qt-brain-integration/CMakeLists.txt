# CMakeLists.txt for C++ Qt Brain Integration
cmake_minimum_required(VERSION 3.16)
project(BrainIntegration VERSION 1.0.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

set(CMAKE_AUTOMOC ON)
set(CMAKE_AUTOUIC ON)

# Find required packages
find_package(Qt6 REQUIRED COMPONENTS Core Gui Widgets Network OpenGL OpenGLWidgets)

# Find ONNX Runtime more robustly
find_path(ONNXRUNTIME_INCLUDE_DIR 
    NAMES onnxruntime_cxx_api.h
    PATHS /usr/local/include /usr/include $ENV{ONNXRUNTIME_HOME}/include
)

find_library(ONNXRUNTIME_LIBRARY 
    NAMES onnxruntime libonnxruntime.so.1
    PATHS /usr/local/lib /usr/lib $ENV{ONNXRUNTIME_HOME}/lib
)

if(ONNXRUNTIME_INCLUDE_DIR AND ONNXRUNTIME_LIBRARY)
    message(STATUS "ONNX Runtime found - includes: ${ONNXRUNTIME_INCLUDE_DIR}, lib: ${ONNXRUNTIME_LIBRARY}")
    add_definitions(-DHAS_ONNXRUNTIME)
    include_directories(${ONNXRUNTIME_INCLUDE_DIR})
    set(ONNXRUNTIME_FOUND TRUE)
else()
    message(WARNING "ONNX Runtime not found - using mock mode")
    set(ONNXRUNTIME_FOUND FALSE)
endif()

# Include directories
include_directories(include)

# Source files for main BrainIntegration application
set(SOURCES
    src/main.cpp
    src/MainWindow.cpp
    src/EmotionalAIManager.cpp
    src/BrainSystemBridge.cpp
    src/NeuralNetworkEngine.cpp
)

set(HEADERS
    include/MainWindow.h
    include/EmotionalAIManager.h
    include/BrainSystemBridge.h
    include/NeuralNetworkEngine.h
)

# Source files for Shimeji Companion
set(SHIMEJI_SOURCES
    src/shimeji_companion_main.cpp
    src/ShimejiConsciousnessWidget.cpp
    src/TelemetryClient.cpp
    src/ChatDialog.cpp
    src/ConsciousnessMapper.cpp
)

set(SHIMEJI_HEADERS
    include/ShimejiConsciousnessWidget.h
    include/TelemetryClient.h
    include/ChatDialog.h
    include/ConsciousnessMapper.h
)

# Create main BrainIntegration executable
add_executable(${PROJECT_NAME} ${SOURCES} ${HEADERS})

# Create Shimeji Companion executable
add_executable(ShimejiCompanion ${SHIMEJI_SOURCES} ${SHIMEJI_HEADERS})

# Link libraries for BrainIntegration
target_link_libraries(${PROJECT_NAME}
    Qt6::Core
    Qt6::Gui
    Qt6::Widgets
    Qt6::Network
    Qt6::OpenGL
    Qt6::OpenGLWidgets
)

if(ONNXRUNTIME_FOUND)
    target_link_libraries(${PROJECT_NAME} ${ONNXRUNTIME_LIBRARY})
endif()

# Link libraries for ShimejiCompanion
target_link_libraries(ShimejiCompanion
    Qt6::Core
    Qt6::Gui
    Qt6::Widgets
    Qt6::Network
)

# Set target properties
# qt6_finalize_executable(${PROJECT_NAME})
# qt6_finalize_executable(ShimejiCompanion)

# Installation
install(TARGETS ${PROJECT_NAME} ShimejiCompanion
    RUNTIME DESTINATION bin
)
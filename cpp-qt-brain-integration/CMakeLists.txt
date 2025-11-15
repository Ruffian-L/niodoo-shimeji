# CMakeLists.txt for Niodoo Shimeji Companion
cmake_minimum_required(VERSION 3.16)
project(ShimejiCompanion VERSION 1.0.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

set(CMAKE_AUTOMOC ON)
set(CMAKE_AUTOUIC ON)

# Find required packages
find_package(Qt6 REQUIRED COMPONENTS Core Gui Widgets Network)

# Include directories
include_directories(include)

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

# Create Shimeji Companion executable
add_executable(ShimejiCompanion ${SHIMEJI_SOURCES} ${SHIMEJI_HEADERS})

# Link libraries for ShimejiCompanion
target_link_libraries(ShimejiCompanion
    Qt6::Core
    Qt6::Gui
    Qt6::Widgets
    Qt6::Network
)

# Installation
install(TARGETS ShimejiCompanion
    RUNTIME DESTINATION bin
)
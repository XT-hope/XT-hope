# Qt6 悬浮按钮项目文件（qmake）

QT += core gui widgets

greaterThan(QT_MAJOR_VERSION, 5): QT += widgets

CONFIG += c++17

# 源文件
SOURCES += qt6_floating_button_cpp_example.cpp

# 编译器标志
QMAKE_CXXFLAGS += -std=c++17

# 目标名称
TARGET = FloatingAIButton

# 模板
TEMPLATE = app

# 输出目录
DESTDIR = ./bin
OBJECTS_DIR = ./build/obj
MOC_DIR = ./build/moc
RCC_DIR = ./build/rcc
UI_DIR = ./build/ui

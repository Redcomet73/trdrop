QT += core gui widgets quick quickcontrols2 multimedia
CONFIG += console c++11 release
CONFIG -= app_bundle debug
TEMPLATE = app
TARGET = trdrop-reference
isEmpty(ORACLE): error("Pass ORACLE=<generated observed directory>")
INCLUDEPATH += $$ORACLE/trdrop
INCLUDEPATH += $$(OpenCV_DIR)/build_64/install/include
LIBS += -L$$(OpenCV_DIR)/build_64/install/x64/mingw/lib \
    -lopencv_core451 -lopencv_imgproc451 -lopencv_imgcodecs451 -lopencv_videoio451 -fopenmp
QMAKE_CXXFLAGS += -fopenmp
equals(PROFILE, 1): DEFINES += BASELINE_PROFILE
equals(TRACE, 1): DEFINES += BASELINE_OBSERVE
SOURCES += $$PWD/reference.cpp
HEADERS += $$files($$ORACLE/trdrop/headers/qml_models/*.h)
HEADERS += $$ORACLE/trdrop/headers/qml_interface/frameprocessing_qml.h \
    $$ORACLE/trdrop/headers/qml_interface/imageconverter_qml.h \
    $$ORACLE/trdrop/headers/qml_interface/imagecomposer_qml.h \
    $$ORACLE/trdrop/headers/qml_interface/renderer_qml.h \
    $$ORACLE/trdrop/headers/qml_interface/exporter_qml.h
RESOURCES += $$ORACLE/trdrop/qml.qrc

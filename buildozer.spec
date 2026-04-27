[app]
title = Server Monitor
package.name = servermonitor
package.domain = org.kjaydev

# Source code setup
source.dir = .
source.include_exts = py,png,jpg,html,js,css,ico,json
source.include_patterns = monitor_core/*,static/*,templates/*
version = 1.0.0

# Requirements
# Note: psutil and gevent require C compilation; Buildozer handles this via recipes
requirements = python3,kivy,flask,flask-socketio,gevent,gevent-websocket,psutil,pyjnius,jinja2,werkzeug,itsdangerous,click,markupsafe

orientation = portrait
fullscreen = 1

# Android specific
android.api = 33
android.minapi = 21
android.archs = arm64-v8a, armeabi-v7a
android.permissions = INTERNET, READ_EXTERNAL_STORAGE, WRITE_EXTERNAL_STORAGE

# Ensure we use the Kivy activity that supports WebView injection
android.entrypoint = org.kivy.android.PythonActivity

[buildozer]
log_level = 2
warn_on_root = 1
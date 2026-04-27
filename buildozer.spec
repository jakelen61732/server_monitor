[app]

warn_on_root = 0

# (str) Icon of the application
icon.filename = %(source.dir)s/icon_512.png

# (str) Icon of the application (adaptive foreground)
# icon.adaptive_foreground.filename = %(source.dir)s/icon_foreground.png

# (str) Icon of the application (adaptive background)
# icon.adaptive_background.filename = %(source.dir)s/icon_background.png

# (str) Title of your application
title = Server Monitor

# (str) Package name
package.name = servermonitor

# (str) Package domain (needed for android packaging)
package.domain = org.kjaydev

# (str) Source code where the main.py live
source.dir = .

# (list) Source files to include
source.include_exts = py,png,jpg,html,js,css,ico,json
source.include_patterns = monitor_core/*,static/*,templates/*

# (str) Application version
version = 1.0.0

# (list) Application requirements
# Packages like gevent and psutil contain C extensions. 
# Buildozer uses 'recipes' to compile these for Android.
requirements = python3, kivy, flask, flask-socketio, gevent, gevent-websocket, psutil, pyjnius, android

# (str) Supported orientations
orientation = portrait

# (bool) Indicate if the application should be fullscreen or not
fullscreen = 0

# (list) Permissions (Internet is required for the Flask server and local loopback)
android.permissions = INTERNET, READ_EXTERNAL_STORAGE, WRITE_EXTERNAL_STORAGE

# This allows the WebView to talk to your local Flask server over HTTP
android.manifest.usesCleartextTraffic = True

# (int) Target Android API
android.api = 33

# (int) Minimum API your APK will support
android.minapi = 21

# (list) The Android architectures to build for
android.archs = arm64-v8a, armeabi-v7a

# (bool) allow backup
android.allow_backup = True

# Ensure we use the Kivy activity that supports WebView injection from main.py
android.entrypoint = org.kivy.android.PythonActivity

[buildozer]
log_level = 2
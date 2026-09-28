[app]
title = Space Shooter 2.0
package.name = spaceshooter
package.domain = org.example

source.dir = .
source.include_exts = py,json
version = 1.0

requirements = python3,kivy

orientation = portrait
fullscreen = 1

# Android
android.api = 33
android.minapi = 21
android.archs = arm64-v8a, armeabi-v7a
android.accept_sdk_license = True
android.permissions =

[buildozer]
log_level = 2
warn_on_root = 1

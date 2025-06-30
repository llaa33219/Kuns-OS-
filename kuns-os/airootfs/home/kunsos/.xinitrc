#!/bin/sh
# Kuns OS X11 Session
# Based on Arch Wiki recommendations

# Basic X11 setup
xset s off
xset -dpms

# Set Kuns OS default wallpaper (Arch Wiki method)
# This will run after Enlightenment starts
(sleep 5 && enlightenment_remote -desktop-bg-set "$HOME/.e/e/backgrounds/kuns-default-wallpaper.png") &

# Start Enlightenment
exec enlightenment_start 
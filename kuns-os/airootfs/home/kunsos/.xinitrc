#!/bin/bash
# Kuns OS .xinitrc

# Kuns OS 바탕화면 자동 설정 (백그라운드)
if [[ -f "$HOME/.wallpaper-setup.sh" ]]; then
    bash "$HOME/.wallpaper-setup.sh" &
fi

# Enlightenment 시작
exec enlightenment_start 
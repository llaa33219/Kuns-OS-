# Kuns OS Auto-start X11
if [[ ! $DISPLAY && $XDG_VTNR -eq 1 ]]; then
  exec startx
fi 
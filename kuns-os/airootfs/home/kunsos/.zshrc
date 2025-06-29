# Kuns OS Default zsh configuration
autoload -U compinit
compinit

# History configuration
HISTFILE=~/.zsh_history
HISTSIZE=1000
SAVEHIST=1000
setopt appendhistory

# Aliases
alias ls='ls --color=auto'
alias ll='ls -la'
alias la='ls -A'
alias grep='grep --color=auto'

# Welcome message
echo "Welcome to Kuns OS!"
echo "Desktop Environment: Enlightenment"
echo "Package Manager: pacman"
echo "Flatpak available for additional applications"

# Add flatpak to PATH
export PATH="$PATH:/var/lib/flatpak/exports/bin:~/.local/share/flatpak/exports/bin"

# Auto-start X11 on tty1
if [[ ! $DISPLAY && $XDG_VTNR -eq 1 ]]; then
  exec startx
fi 
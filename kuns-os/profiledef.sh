#!/usr/bin/env bash
# shellcheck disable=SC2034

iso_name="kunsos"
iso_label="KUNS_OS_$(date --date="@${SOURCE_DATE_EPOCH:-$(date +%s)}" +%Y%m)"
iso_publisher="Kuns OS <https://github.com/kunsos>"
iso_application="Kuns OS Live/Install DVD"
iso_version="$(date --date="@${SOURCE_DATE_EPOCH:-$(date +%s)}" +%Y.%m.%d)"
install_dir="kunsos"
buildmodes=('iso')
bootmodes=('bios.syslinux.mbr' 'bios.syslinux.eltorito'
           'uefi-ia32.systemd-boot.esp' 'uefi-x64.systemd-boot.esp'
           'uefi-ia32.systemd-boot.eltorito' 'uefi-x64.systemd-boot.eltorito')
arch="x86_64"
pacman_conf="pacman.conf"
airootfs_image_type="squashfs"
airootfs_image_tool_options=('-comp' 'xz' '-Xbcj' 'x86' '-b' '1M' '-Xdict-size' '1M')
bootstrap_tarball_compression=('zstd' '-c' '-T0' '--auto-threads=logical' '--long' '-19')
file_permissions=(
  ["/etc/shadow"]="0:0:400"
  ["/etc/sudoers.d/wheel"]="0:0:440"
  ["/root"]="0:0:750"
  ["/root/.automated_script.sh"]="0:0:755"
  ["/root/.gnupg"]="0:0:700"
  ["/usr/local/bin/choose-mirror"]="0:0:755"
  ["/usr/local/bin/Installation_guide"]="0:0:755"
  ["/usr/local/bin/livecd-sound"]="0:0:755"
  ["/usr/local/bin/setup-flatpak"]="0:0:755"
  ["/usr/local/bin/kuns-installer"]="0:0:755"
  ["/home/kunsos"]="1000:1000:755"
  ["/home/kunsos/.zshrc"]="1000:1000:644"
  ["/home/kunsos/.xinitrc"]="1000:1000:755"
  ["/home/kunsos/.bash_profile"]="1000:1000:644"
  ["/home/kunsos/Desktop"]="1000:1000:755"
  ["/home/kunsos/Desktop/Install-Kuns-OS.desktop"]="1000:1000:755"
  ["/home/kunsos/Desktop/Welcome.desktop"]="1000:1000:755"
  ["/home/kunsos/.e"]="1000:1000:755"
  ["/usr/share/enlightenment"]="0:0:755"
  ["/home/kunsos/.e/e/backgrounds/kuns-default-wallpaper.png"]="1000:1000:644"
)

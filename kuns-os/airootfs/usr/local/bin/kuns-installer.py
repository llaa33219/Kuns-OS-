#!/usr/bin/env python3

import sys
import os
import subprocess
import threading
import time
import tempfile
import json
import shutil
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *



class ArchInstallThread(QThread):
    progress = pyqtSignal(int)
    status = pyqtSignal(str)
    finished = pyqtSignal(bool, str)
    log_output = pyqtSignal(str)

    def __init__(self, config):
        super().__init__()
        self.config = config
        self.mount_point = "/mnt"
        self.boot_mount = "/mnt/boot"

    def run(self):
        try:
            self.status.emit("Starting installation...")
            self.progress.emit(0)
            
            # Step 1: Prepare disk
            if not self._prepare_disk():
                self.finished.emit(False, "Disk preparation failed")
                return
            self.progress.emit(15)
            
            # Step 2: Create filesystems
            if not self._create_filesystems():
                self.finished.emit(False, "Filesystem creation failed")
                return
            self.progress.emit(25)
            
            # Step 3: Mount filesystems
            if not self._mount_filesystems():
                self.finished.emit(False, "Filesystem mounting failed")
                return
            self.progress.emit(35)
            
            # Step 4: Install base system
            if not self._install_base_system():
                self.finished.emit(False, "Base system installation failed")
                return
            self.progress.emit(60)
            
            # Step 5: Generate fstab
            if not self._generate_fstab():
                self.finished.emit(False, "fstab generation failed")
                return
            self.progress.emit(65)
            
            # Step 6: Configure system
            if not self._configure_system():
                self.finished.emit(False, "System configuration failed")
                return
            self.progress.emit(85)
            
            # Step 7: Install bootloader
            if not self._install_bootloader():
                self.finished.emit(False, "Bootloader installation failed")
                return
            self.progress.emit(95)
            
            # Step 8: Final cleanup
            self._cleanup_installation()
            self.progress.emit(100)
            
            self.status.emit("Installation completed successfully!")
            self.finished.emit(True, "Kuns OS installation completed successfully!")
            
        except Exception as e:
            self.log_output.emit(f"Installation error: {str(e)}")
            self.finished.emit(False, f"Installation error: {str(e)}")

    def _run_command(self, cmd, description="", check=True):
        """Execute a command and return success status"""
        try:
            self.log_output.emit(f"Executing: {' '.join(cmd) if isinstance(cmd, list) else cmd}")
            
            if isinstance(cmd, str):
                process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, 
                                         stderr=subprocess.STDOUT, universal_newlines=True)
            else:
                process = subprocess.Popen(cmd, stdout=subprocess.PIPE, 
                                         stderr=subprocess.STDOUT, universal_newlines=True)
            
            output = ""
            for line in iter(process.stdout.readline, ''):
                line = line.strip()
                if line:
                    output += line + "\n"
                    self.log_output.emit(line)
            
            process.wait()
            
            if check and process.returncode != 0:
                self.log_output.emit(f"Command failed with return code {process.returncode}")
                return False
            
            return True
            
        except Exception as e:
            self.log_output.emit(f"Command execution error: {str(e)}")
            return False

    def _prepare_disk(self):
        """Prepare disk for installation"""
        self.status.emit("Preparing disk...")
        disk = self.config.get('disk', '/dev/sda')
        
        # Check if disk exists
        if not os.path.exists(disk):
            self.log_output.emit(f"Disk {disk} does not exist")
            return False
        
        # Unmount any existing partitions
        self.log_output.emit("Unmounting existing partitions...")
        self._run_command(f"umount -R {self.mount_point}", check=False)
        
        # Create new partition table
        self.log_output.emit("Creating new partition table...")
        if not self._run_command(f"parted -s {disk} mklabel gpt"):
            return False
        
        # Create EFI partition (512MB)
        self.log_output.emit("Creating EFI partition...")
        if not self._run_command(f"parted -s {disk} mkpart primary fat32 1MiB 513MiB"):
            return False
        if not self._run_command(f"parted -s {disk} set 1 esp on"):
            return False
        
        # Create root partition (rest of disk)
        self.log_output.emit("Creating root partition...")
        if not self._run_command(f"parted -s {disk} mkpart primary ext4 513MiB 100%"):
            return False
        
        # Wait for partitions to be recognized
        time.sleep(2)
        self._run_command("partprobe", check=False)
        time.sleep(1)
        
        return True

    def _create_filesystems(self):
        """Create filesystems on partitions"""
        self.status.emit("Creating filesystems...")
        disk = self.config.get('disk', '/dev/sda')
        
        # Determine partition names
        if 'nvme' in disk or 'mmc' in disk:
            efi_part = f"{disk}p1"
            root_part = f"{disk}p2"
        else:
            efi_part = f"{disk}1"
            root_part = f"{disk}2"
        
        # Format EFI partition
        self.log_output.emit("Formatting EFI partition...")
        if not self._run_command(f"mkfs.fat -F32 {efi_part}"):
            return False
        
        # Format root partition
        self.log_output.emit("Formatting root partition...")
        if not self._run_command(f"mkfs.ext4 -F {root_part}"):
            return False
        
        # Store partition info for later use
        self.efi_partition = efi_part
        self.root_partition = root_part
        
        return True

    def _mount_filesystems(self):
        """Mount filesystems"""
        self.status.emit("Mounting filesystems...")
        
        # Create root mount point
        os.makedirs(self.mount_point, exist_ok=True)
        
        # Mount root partition first
        self.log_output.emit("Mounting root partition...")
        if not self._run_command(f"mount {self.root_partition} {self.mount_point}"):
            return False
        
        # Create boot mount point after root is mounted
        self.log_output.emit("Creating boot mount point...")
        os.makedirs(self.boot_mount, exist_ok=True)
        
        # Mount EFI partition
        self.log_output.emit("Mounting EFI partition...")
        if not self._run_command(f"mount {self.efi_partition} {self.boot_mount}"):
            return False
        
        return True

    def _install_base_system(self):
        """Install base system using pacstrap"""
        self.status.emit("Installing base system...")
        
        # Get packages to install
        packages = self._get_packages_list()
        packages_str = " ".join(packages)
        
        self.log_output.emit(f"Installing packages: {packages_str}")
        
        # Use pacstrap to install base system
        cmd = f"pacstrap {self.mount_point} {packages_str}"
        if not self._run_command(cmd):
            return False
        
        return True

    def _get_packages_list(self):
        """Get list of packages to install"""
        base_packages = [
            "base", "base-devel", "linux", "linux-firmware",
            "networkmanager", "grub", "efibootmgr", "dosfstools",
            "mtools", "os-prober", "sudo", "nano", "vim"
        ]
        
        # Add Kuns OS specific packages
        kuns_packages = [
            "enlightenment", "terminology", "lightdm", "lightdm-gtk-greeter",
            "firefox", "dolphin", "kate", "konsole", "gwenview",
            "nautilus", "gnome-calculator", "gnome-screenshot",
            "flatpak", "noto-fonts", "noto-fonts-cjk", "ttf-dejavu", "ttf-liberation"
        ]
        
        # Add user selected packages
        user_packages = self.config.get('packages', [])
        
        all_packages = base_packages + kuns_packages + user_packages
        return list(set(all_packages))  # Remove duplicates

    def _generate_fstab(self):
        """Generate fstab file"""
        self.status.emit("Generating fstab...")
        
        self.log_output.emit("Generating fstab file...")
        if not self._run_command(f"genfstab -U {self.mount_point} >> {self.mount_point}/etc/fstab"):
            return False
        
        return True

    def _configure_system(self):
        """Configure the installed system"""
        self.status.emit("Configuring system...")
        
        # Set timezone
        timezone = self.config.get('timezone', 'UTC')
        self.log_output.emit(f"Setting timezone to {timezone}")
        if not self._run_command(f"arch-chroot {self.mount_point} ln -sf /usr/share/zoneinfo/{timezone} /etc/localtime"):
            return False
        if not self._run_command(f"arch-chroot {self.mount_point} hwclock --systohc"):
            return False
        
        # Configure locale
        locale = self.config.get('locale', 'en_US.UTF-8')
        self.log_output.emit(f"Setting locale to {locale}")
        
        # Enable the locale in /etc/locale.gen
        if not self._run_command(f"arch-chroot {self.mount_point} sed -i 's/^#{locale}/{locale}/' /etc/locale.gen"):
            return False
        
        # Also ensure en_US.UTF-8 is always available
        if locale != 'en_US.UTF-8':
            if not self._run_command(f"arch-chroot {self.mount_point} sed -i 's/^#en_US.UTF-8/en_US.UTF-8/' /etc/locale.gen"):
                return False
        
        if not self._run_command(f"arch-chroot {self.mount_point} locale-gen"):
            return False
        
        # Set system locale
        with open(f"{self.mount_point}/etc/locale.conf", "w") as f:
            f.write(f"LANG={locale}\n")
        
        # Set keyboard layout
        keymap = self.config.get('keymap', 'us')
        with open(f"{self.mount_point}/etc/vconsole.conf", "w") as f:
            f.write(f"KEYMAP={keymap}\n")
        
        # Set hostname
        hostname = self.config.get('hostname', 'kuns-os')
        with open(f"{self.mount_point}/etc/hostname", "w") as f:
            f.write(f"{hostname}\n")
        
        # Configure hosts file
        hosts_content = f"""127.0.0.1	localhost
::1		localhost
127.0.1.1	{hostname}.localdomain	{hostname}
"""
        with open(f"{self.mount_point}/etc/hosts", "w") as f:
            f.write(hosts_content)
        
        # Set root password
        root_password = self.config.get('root_password', '')
        if root_password:
            self.log_output.emit("Setting root password...")
            if not self._run_command(f"arch-chroot {self.mount_point} bash -c 'echo \"root:{root_password}\" | chpasswd'"):
                return False
        
        # Create user
        username = self.config.get('username', 'kunsos')
        user_password = self.config.get('password', '')
        
        if username and user_password:
            self.log_output.emit(f"Creating user {username}...")
            if not self._run_command(f"arch-chroot {self.mount_point} useradd -m -G wheel -s /bin/bash {username}"):
                return False
            if not self._run_command(f"arch-chroot {self.mount_point} bash -c 'echo \"{username}:{user_password}\" | chpasswd'"):
                return False
        
        # Configure sudo
        self.log_output.emit("Configuring sudo...")
        if not self._run_command(f"arch-chroot {self.mount_point} sed -i 's/^# %wheel ALL=(ALL:ALL) ALL/%wheel ALL=(ALL:ALL) ALL/' /etc/sudoers"):
            return False
        
        # Enable NetworkManager
        self.log_output.emit("Enabling NetworkManager...")
        if not self._run_command(f"arch-chroot {self.mount_point} systemctl enable NetworkManager"):
            return False
        
        # Enable LightDM
        self.log_output.emit("Enabling LightDM...")
        if not self._run_command(f"arch-chroot {self.mount_point} systemctl enable lightdm"):
            return False
        
        return True

    def _install_bootloader(self):
        """Install GRUB bootloader"""
        self.status.emit("Installing bootloader...")
        
        disk = self.config.get('disk', '/dev/sda')
        
        # Determine partition names
        if 'nvme' in disk or 'mmc' in disk:
            boot_part = f"{disk}p1"
        else:
            boot_part = f"{disk}1"
        
        # Set boot flag on EFI partition
        self.log_output.emit("Setting boot flag on EFI partition...")
        self._run_command(f"parted {disk} set 1 boot on", check=False)
        
        # Create EFI boot directory
        self.log_output.emit("Creating EFI boot directory...")
        if not self._run_command(f"arch-chroot {self.mount_point} mkdir -p /boot/EFI"):
            return False
        
        # Try both installation methods for maximum compatibility
        self.log_output.emit("Installing GRUB for both EFI and BIOS...")
        
        # EFI installation
        efi_success = self._run_command(f"arch-chroot {self.mount_point} grub-install --target=x86_64-efi --efi-directory=/boot --bootloader-id=KunsOS --no-nvram --removable", check=False)
        
        # BIOS installation (for fallback)
        bios_success = self._run_command(f"arch-chroot {self.mount_point} grub-install --target=i386-pc {disk}", check=False)
        
        if efi_success:
            self.log_output.emit("EFI GRUB installation successful")
        if bios_success:
            self.log_output.emit("BIOS GRUB installation successful")
        
        if not efi_success and not bios_success:
            self.log_output.emit("WARNING: Both EFI and BIOS installation failed!")
            # Don't return False, continue with config generation
        
        # Generate GRUB configuration
        self.log_output.emit("Generating GRUB configuration...")
        if not self._run_command(f"arch-chroot {self.mount_point} grub-mkconfig -o /boot/grub/grub.cfg"):
            return False
        
        # Create multiple fallback boot entries
        self.log_output.emit("Creating fallback boot entries...")
        
        # Standard EFI fallback
        self._run_command(f"arch-chroot {self.mount_point} mkdir -p /boot/EFI/BOOT", check=False)
        self._run_command(f"arch-chroot {self.mount_point} cp /boot/EFI/KunsOS/grubx64.efi /boot/EFI/BOOT/BOOTX64.EFI", check=False)
        
        # Create simple GRUB config for direct booting
        grub_standalone = f"""
set root='hd0,gpt2'
linux /boot/vmlinuz-linux root=UUID=$(blkid -s UUID -o value {self.root_partition}) rw
initrd /boot/initramfs-linux.img
boot
"""
        
        with open(f"{self.mount_point}/boot/grub/grub-standalone.cfg", "w") as f:
            f.write(grub_standalone)
        
        # Make MBR bootable as well
        self.log_output.emit("Making disk bootable...")
        self._run_command(f"parted {disk} set 1 legacy_boot on", check=False)
        
        return True

    def _cleanup_installation(self):
        """Clean up after installation"""
        self.status.emit("Cleaning up...")
        
        # Unmount filesystems
        self.log_output.emit("Unmounting filesystems...")
        self._run_command(f"umount -R {self.mount_point}", check=False)
        
        self.log_output.emit("Installation cleanup completed")

class DiskSelectionWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.button_group = QButtonGroup()  # Radio button grouping
        self.setup_ui()
        self.refresh_disks()
        
    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Title
        title = QLabel("Installation Disk Selection")
        title.setStyleSheet("font-size: 18px; font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(title)
        
        # Description
        desc = QLabel("Select the disk where Kuns OS will be installed. All data on the selected disk will be completely erased!")
        desc.setStyleSheet("color: #e74c3c; font-weight: bold; margin-bottom: 15px;")
        desc.setWordWrap(True)
        layout.addWidget(desc)
        
        # Disk list
        self.disk_table = QTableWidget()
        self.disk_table.setColumnCount(4)
        self.disk_table.setHorizontalHeaderLabels(["Select", "Device", "Size", "Model"])
        self.disk_table.horizontalHeader().setStretchLastSection(True)
        self.disk_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.disk_table.setAlternatingRowColors(True)
        self.disk_table.verticalHeader().setVisible(False)
        self.disk_table.setShowGrid(True)
        
        # Set column widths
        self.disk_table.setColumnWidth(0, 80)
        self.disk_table.setColumnWidth(1, 120)
        self.disk_table.setColumnWidth(2, 100)
        
        layout.addWidget(self.disk_table)
        
        # Control buttons
        button_layout = QHBoxLayout()
        
        refresh_btn = QPushButton("🔄 Refresh Disks")
        refresh_btn.clicked.connect(self.refresh_disks)
        refresh_btn.setStyleSheet("padding: 8px 15px;")
        button_layout.addWidget(refresh_btn)
        
        button_layout.addStretch()
        
        # Selected disk info
        self.selected_info = QLabel("No disk selected")
        self.selected_info.setStyleSheet("background: rgba(52, 152, 219, 0.1); padding: 10px; border-radius: 5px; font-weight: bold;")
        button_layout.addWidget(self.selected_info)
        
        layout.addLayout(button_layout)
        
        # Warning
        warning = QLabel("⚠️ WARNING: ALL DATA ON THE SELECTED DISK WILL BE PERMANENTLY DELETED!\nPlease backup important data before proceeding.")
        warning.setStyleSheet("color: #e74c3c; font-weight: bold; background: rgba(231, 76, 60, 0.1); padding: 15px; border-radius: 5px; margin: 15px 0; border: 2px solid #e74c3c;")
        warning.setWordWrap(True)
        layout.addWidget(warning)
        
    def refresh_disks(self):
        # Clear existing data
        self.disk_table.setRowCount(0)
        for button in self.button_group.buttons():
            self.button_group.removeButton(button)
        
        try:
            # Get all block devices
            result = subprocess.run(['lsblk', '-dpno', 'NAME,SIZE,MODEL,TYPE'], 
                                  capture_output=True, text=True, check=True)
            
            disks = []
            for line in result.stdout.strip().split('\n'):
                if line and '/dev/' in line:
                    parts = line.split(None, 3)
                    if len(parts) >= 3:
                        device = parts[0]
                        size = parts[1]
                        model = parts[2] if len(parts) > 2 else 'Unknown'
                        device_type = parts[3] if len(parts) > 3 else 'disk'
                        
                        # Filter out loop devices, sr (optical), and other non-disk devices
                        if ('loop' not in device and 'sr' not in device and 
                            'ram' not in device and 'zram' not in device and
                            device_type == 'disk'):
                            
                            # Additional check for minimum size (at least 1GB)
                            try:
                                size_bytes = self._parse_size(size)
                                if size_bytes >= 1024 * 1024 * 1024:  # 1GB minimum
                                    disks.append({
                                        'device': device,
                                        'size': size,
                                        'model': model,
                                        'size_bytes': size_bytes
                                    })
                            except ValueError:
                                # If size parsing fails, still include the disk
                                disks.append({
                                    'device': device,
                                    'size': size,
                                    'model': model,
                                    'size_bytes': 0
                                })
            
            # Sort disks by size (largest first)
            disks.sort(key=lambda x: x['size_bytes'], reverse=True)
            
            if not disks:
                QMessageBox.warning(self, "No Disks Found", 
                                  "No suitable installation disks found.\n"
                                  "Please ensure you have at least one disk with 1GB+ capacity.")
                return
            
            self.disk_table.setRowCount(len(disks))
            for i, disk in enumerate(disks):
                # Radio button
                radio = QRadioButton()
                if i == 0:  # Select first (largest) disk by default
                    radio.setChecked(True)
                    self._update_selected_info(disk)
                
                radio.toggled.connect(lambda checked, d=disk: self._on_disk_selected(checked, d))
                self.button_group.addButton(radio)
                
                # Center the radio button in the cell
                radio_widget = QWidget()
                radio_layout = QHBoxLayout(radio_widget)
                radio_layout.addWidget(radio)
                radio_layout.setAlignment(Qt.AlignCenter)
                radio_layout.setContentsMargins(0, 0, 0, 0)
                
                self.disk_table.setCellWidget(i, 0, radio_widget)
                
                # Disk information
                device_item = QTableWidgetItem(disk['device'])
                device_item.setFlags(device_item.flags() & ~Qt.ItemIsEditable)
                self.disk_table.setItem(i, 1, device_item)
                
                size_item = QTableWidgetItem(disk['size'])
                size_item.setFlags(size_item.flags() & ~Qt.ItemIsEditable)
                self.disk_table.setItem(i, 2, size_item)
                
                model_item = QTableWidgetItem(disk['model'])
                model_item.setFlags(model_item.flags() & ~Qt.ItemIsEditable)
                self.disk_table.setItem(i, 3, model_item)
                
        except subprocess.CalledProcessError as e:
            QMessageBox.critical(self, "Error", f"Failed to retrieve disk information:\n{e}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Unexpected error while scanning disks:\n{e}")
    
    def _parse_size(self, size_str):
        """Parse size string (e.g., '8G', '500M') to bytes"""
        size_str = size_str.upper().strip()
        
        multipliers = {
            'B': 1,
            'K': 1024,
            'M': 1024**2,
            'G': 1024**3,
            'T': 1024**4
        }
        
        for suffix, multiplier in multipliers.items():
            if size_str.endswith(suffix):
                try:
                    number = float(size_str[:-1])
                    return int(number * multiplier)
                except ValueError:
                    pass
        
        # Try parsing as plain number (bytes)
        try:
            return int(float(size_str))
        except ValueError:
            raise ValueError(f"Cannot parse size: {size_str}")
    
    def _on_disk_selected(self, checked, disk):
        """Handle disk selection"""
        if checked:
            self._update_selected_info(disk)
    
    def _update_selected_info(self, disk):
        """Update selected disk information display"""
        self.selected_info.setText(f"Selected: {disk['device']} ({disk['size']}) - {disk['model']}")
    
    def get_selected_disk(self):
        """Get the currently selected disk device path"""
        for i in range(self.disk_table.rowCount()):
            radio_widget = self.disk_table.cellWidget(i, 0)
            if radio_widget:
                radio = radio_widget.findChild(QRadioButton)
                if radio and radio.isChecked():
                    return self.disk_table.item(i, 1).text()
        return None
    
    def validate_selection(self):
        """Validate that a disk is selected"""
        selected = self.get_selected_disk()
        if not selected:
            QMessageBox.warning(self, "No Disk Selected", 
                              "Please select a disk for installation.")
            return False
        return True

class UserConfigWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.setup_ui()
        
    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Title
        title = QLabel("User Settings")
        title.setStyleSheet("font-size: 18px; font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(title)
        
        # Form
        form = QFormLayout()
        
        self.hostname_edit = QLineEdit("kuns-os")
        self.username_edit = QLineEdit("kunsos")
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.Password)
        self.password_confirm_edit = QLineEdit()
        self.password_confirm_edit.setEchoMode(QLineEdit.Password)
        self.root_password_edit = QLineEdit()
        self.root_password_edit.setEchoMode(QLineEdit.Password)
        
        form.addRow("Computer Name:", self.hostname_edit)
        form.addRow("Username:", self.username_edit)
        form.addRow("User Password:", self.password_edit)
        form.addRow("Confirm Password:", self.password_confirm_edit)
        form.addRow("Root Password:", self.root_password_edit)
        
        layout.addLayout(form)
        
        # Timezone settings
        timezone_group = QGroupBox("Timezone Settings")
        timezone_layout = QHBoxLayout(timezone_group)
        
        self.timezone_combo = QComboBox()
        self.timezone_combo.addItems([
            "UTC", "Asia/Seoul", "America/New_York", "Europe/London", 
            "Asia/Tokyo", "Australia/Sydney"
        ])
        timezone_layout.addWidget(QLabel("Timezone:"))
        timezone_layout.addWidget(self.timezone_combo)
        
        layout.addWidget(timezone_group)
        
        # Keyboard layout
        keyboard_group = QGroupBox("Keyboard Settings")
        keyboard_layout = QHBoxLayout(keyboard_group)
        
        self.keyboard_combo = QComboBox()
        self.keyboard_combo.addItems(["us", "kr", "jp", "de", "fr"])
        self.keyboard_combo.setCurrentText("us")  # Default to US layout
        keyboard_layout.addWidget(QLabel("Keyboard Layout:"))
        keyboard_layout.addWidget(self.keyboard_combo)
        
        layout.addWidget(keyboard_group)
        
        layout.addStretch()
        
    def validate(self):
        if not self.hostname_edit.text().strip():
            QMessageBox.warning(self, "Error", "Please enter a computer name.")
            return False
        if not self.username_edit.text().strip():
            QMessageBox.warning(self, "Error", "Please enter a username.")
            return False
        if not self.password_edit.text():
            QMessageBox.warning(self, "Error", "Please enter a user password.")
            return False
        if self.password_edit.text() != self.password_confirm_edit.text():
            QMessageBox.warning(self, "Error", "Passwords do not match.")
            return False
        if not self.root_password_edit.text():
            QMessageBox.warning(self, "Error", "Please enter a root password.")
            return False
        return True
    
    def get_config(self):
        return {
            'hostname': self.hostname_edit.text().strip(),
            'username': self.username_edit.text().strip(),
            'password': self.password_edit.text(),
            'root_password': self.root_password_edit.text(),
            'timezone': self.timezone_combo.currentText(),
            'keyboard': self.keyboard_combo.currentText()
        }

class PackageSelectionWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.setup_ui()
        
    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Title
        title = QLabel("Kuns OS Installation Options")
        title.setStyleSheet("font-size: 18px; font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(title)
        
        # Kuns OS description
        kuns_desc = QLabel("""
        <div style="background: rgba(52, 152, 219, 0.1); padding: 15px; border-radius: 5px; margin: 10px 0;">
        <h3 style="color: #3498db; margin: 0 0 10px 0;">Kuns OS Features</h3>
        <p style="margin: 5px 0;"><b>• Enlightenment</b> - Beautiful and lightweight desktop environment</p>
        <p style="margin: 5px 0;"><b>• KDE + GNOME Apps</b> - Best tools all in one</p>
        <p style="margin: 5px 0;"><b>• Flatpak Support</b> - Easy app installation</p>
        <p style="margin: 5px 0;"><b>• Multi-language Support</b> - Perfect international environment</p>
        </div>
        """)
        kuns_desc.setWordWrap(True)
        layout.addWidget(kuns_desc)
        
        # Installation type selection
        install_group = QGroupBox("Installation Type Selection")
        install_layout = QVBoxLayout(install_group)
        
        self.install_radio_full = QRadioButton("Full Installation (Recommended)")
        self.install_radio_full.setChecked(True)
        self.install_radio_minimal = QRadioButton("Minimal Installation")
        
        install_layout.addWidget(self.install_radio_full)
        install_layout.addWidget(self.install_radio_minimal)
        
        # Add descriptions
        full_desc = QLabel("• Enlightenment + KDE/GNOME Apps + Flatpak + Additional Software")
        full_desc.setStyleSheet("color: #27ae60; margin-left: 20px; font-size: 12px;")
        install_layout.addWidget(full_desc)
        
        minimal_desc = QLabel("• Basic System + Enlightenment only")
        minimal_desc.setStyleSheet("color: #7f8c8d; margin-left: 20px; font-size: 12px;")
        install_layout.addWidget(minimal_desc)
        
        layout.addWidget(install_group)
        
        # Additional software (full installation only)
        self.software_group = QGroupBox("Additional Software")
        software_layout = QVBoxLayout(self.software_group)
        
        # Development tools
        dev_group = QGroupBox("Development Tools")
        dev_layout = QVBoxLayout(dev_group)
        
        self.vscode_check = QCheckBox("Visual Studio Code")
        self.vscode_check.setChecked(True)
        self.vim_neovim_check = QCheckBox("Vim & Neovim")
        self.git_check = QCheckBox("Git & Development Tools")
        self.git_check.setChecked(True)
        
        dev_layout.addWidget(self.vscode_check)
        dev_layout.addWidget(self.vim_neovim_check)
        dev_layout.addWidget(self.git_check)
        
        software_layout.addWidget(dev_group)
        
        # Multimedia
        media_group = QGroupBox("Multimedia")
        media_layout = QVBoxLayout(media_group)
        
        self.gimp_check = QCheckBox("GIMP (Image Editor)")
        self.vlc_check = QCheckBox("VLC (Media Player)")
        self.vlc_check.setChecked(True)
        self.audacity_check = QCheckBox("Audacity (Audio Editor)")
        
        media_layout.addWidget(self.gimp_check)
        media_layout.addWidget(self.vlc_check)
        media_layout.addWidget(self.audacity_check)
        
        software_layout.addWidget(media_group)
        
        # Office & Documents
        office_group = QGroupBox("Office & Documents")
        office_layout = QVBoxLayout(office_group)
        
        self.libreoffice_check = QCheckBox("LibreOffice (Office Suite)")
        self.libreoffice_check.setChecked(True)
        self.thunderbird_check = QCheckBox("Thunderbird (Email Client)")
        
        office_layout.addWidget(self.libreoffice_check)
        office_layout.addWidget(self.thunderbird_check)
        
        software_layout.addWidget(office_group)
        
        layout.addWidget(self.software_group)
        
        # Connect radio buttons
        self.install_radio_full.toggled.connect(self._on_install_type_changed)
        self.install_radio_minimal.toggled.connect(self._on_install_type_changed)
        
        layout.addStretch()
        
    def _on_install_type_changed(self):
        self.software_group.setEnabled(self.install_radio_full.isChecked())
        
    def get_packages(self):
        # Kuns OS base packages
        base_packages = [
            "base", "linux", "linux-firmware", "grub", "efibootmgr", "networkmanager",
            "enlightenment", "lightdm", "lightdm-gtk-greeter",
            "xorg", "xorg-server", "xorg-xinit",
            "pulseaudio", "pulseaudio-alsa",
            "flatpak", "firefox", "noto-fonts", "noto-fonts-cjk", "ttf-dejavu", "ttf-liberation"
        ]
        
        # KDE apps (Kuns OS default)
        kde_apps = [
            "ark", "dolphin", "gwenview", "kate", "konsole", "kwrite", 
            "okular", "spectacle"
        ]
        
        # GNOME apps (Kuns OS default)
        gnome_apps = [
            "gnome-calculator", "gnome-disk-utility", "gnome-screenshot",
            "gnome-system-monitor", "gnome-terminal", "gnome-text-editor",
            "nautilus", "evince", "gedit"
        ]
        
        # Basic utilities
        utilities = [
            "gparted", "pavucontrol", "network-manager-applet",
            "sudo", "nano", "vim", "wget", "curl", "zip", "unzip"
        ]
        
        packages = base_packages + kde_apps + gnome_apps + utilities
        
        if self.install_radio_full.isChecked():
            # 추가 소프트웨어
            if self.vscode_check.isChecked():
                packages.append("code")
            if self.vim_neovim_check.isChecked():
                packages.extend(["vim", "neovim"])
            if self.git_check.isChecked():
                packages.extend(["git", "base-devel"])
            if self.gimp_check.isChecked():
                packages.append("gimp")
            if self.vlc_check.isChecked():
                packages.append("vlc")
            if self.audacity_check.isChecked():
                packages.append("audacity")
            if self.libreoffice_check.isChecked():
                packages.append("libreoffice-fresh")
            if self.thunderbird_check.isChecked():
                packages.append("thunderbird")
        
        return packages

class InstallProgressWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.setup_ui()
        
    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Title
        title = QLabel("Installing Kuns OS...")
        title.setStyleSheet("font-size: 18px; font-weight: bold; margin-bottom: 20px;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(True)
        layout.addWidget(self.progress_bar)
        
        # Status
        self.status_label = QLabel("Preparing installation...")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("font-size: 14px; margin: 10px;")
        layout.addWidget(self.status_label)
        
        # Log output
        log_group = QGroupBox("Installation Log")
        log_layout = QVBoxLayout(log_group)
        
        self.log_text = QTextEdit()
        self.log_text.setMaximumHeight(200)
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Consolas", 9))
        log_layout.addWidget(self.log_text)
        
        layout.addWidget(log_group)
        
        layout.addStretch()
    
    def update_progress(self, value):
        self.progress_bar.setValue(value)
    
    def update_status(self, text):
        self.status_label.setText(text)
    
    def add_log(self, text):
        self.log_text.append(text)
        self.log_text.ensureCursorVisible()



class KunsInstaller(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Kuns OS Installer")
        self.setGeometry(200, 200, 800, 600)
        self.setMinimumSize(700, 500)
        
        self.current_page = 0
        self.install_thread = None
        
        self.setup_ui()
        self.apply_styles()
        
    def setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        
        # Header
        header = QWidget()
        header_layout = QHBoxLayout(header)
        
        title_label = QLabel("Kuns OS Installer")
        title_label.setStyleSheet("font-size: 24px; font-weight: bold; color: #2980b9; margin: 0 20px;")
        header_layout.addWidget(title_label)
        
        header_layout.addStretch()
        
        version_label = QLabel("v2.1 (Enlightenment)")
        version_label.setStyleSheet("color: #7f8c8d; font-size: 12px;")
        header_layout.addWidget(version_label)
        
        layout.addWidget(header)
        
        # Page stack
        self.stack = QStackedWidget()
        
        # Pages
        self.welcome_page = self.create_welcome_page()
        self.disk_page = DiskSelectionWidget()
        self.user_page = UserConfigWidget()
        self.package_page = PackageSelectionWidget()
        self.progress_page = InstallProgressWidget()
        self.finish_page = self.create_finish_page()
        
        self.stack.addWidget(self.welcome_page)
        self.stack.addWidget(self.disk_page)
        self.stack.addWidget(self.user_page)
        self.stack.addWidget(self.package_page)
        self.stack.addWidget(self.progress_page)
        self.stack.addWidget(self.finish_page)
        
        layout.addWidget(self.stack)
        
        # Buttons
        self.create_buttons(layout)
        
    def create_welcome_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        
        layout.addStretch()
        
        welcome_text = QLabel("""
        <div style="text-align: center;">
        <h1 style="color: #2980b9; margin-bottom: 20px;">Welcome to Kuns OS!</h1>
        
        <div style="background: rgba(52, 152, 219, 0.1); padding: 20px; border-radius: 10px; margin: 20px 0;">
        <h2 style="color: #3498db; margin-top: 0;">Kuns OS Special Features</h2>
        
        <div style="text-align: left; margin: 15px 0;">
        <p style="margin: 8px 0;"><b>Enlightenment Desktop</b><br>
        &nbsp;&nbsp;&nbsp;&nbsp;Beautiful and lightweight desktop environment</p>
        
        <p style="margin: 8px 0;"><b>Best KDE + GNOME Apps</b><br>
        &nbsp;&nbsp;&nbsp;&nbsp;Dolphin, Kate, Nautilus, GIMP and more useful tools</p>
        
        <p style="margin: 8px 0;"><b>Flatpak Support</b><br>
        &nbsp;&nbsp;&nbsp;&nbsp;Easy app installation and management</p>
        
        <p style="margin: 8px 0;"><b>Multi-language Support</b><br>
        &nbsp;&nbsp;&nbsp;&nbsp;Optimized environment for global users</p>
        </div>
        </div>
        
        <div style="background: rgba(231, 76, 60, 0.1); padding: 15px; border-radius: 8px; margin: 20px 0;">
        <p style="color: #e74c3c; font-weight: bold; margin: 0;">
        Important Notice<br>
        All data on the selected disk will be deleted during installation.<br>
        Please backup important data beforehand.
        </p>
        </div>
        </div>
        """)
        welcome_text.setWordWrap(True)
        welcome_text.setAlignment(Qt.AlignCenter)
        layout.addWidget(welcome_text)
        
        layout.addStretch()
        
        return page
    
    def create_finish_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        
        layout.addStretch()
        
        finish_text = QLabel("""
        <div style="text-align: center;">
        <h1 style="color: #27ae60; margin-bottom: 20px;">Kuns OS Installation Complete!</h1>
        
        <p style="font-size: 16px; margin: 15px 0;">
        Congratulations! Kuns OS has been installed successfully.
        </p>
        
        <div style="background: rgba(52, 152, 219, 0.1); padding: 20px; border-radius: 10px; margin: 20px;">
        <h3 style="color: #3498db; margin-top: 0;">Next Steps</h3>
        <div style="text-align: left;">
        <p><b>1.</b> Remove installation media (USB/DVD)</p>
        <p><b>2.</b> Restart your computer</p>
        <p><b>3.</b> Enjoy Enlightenment desktop!</p>
        <p><b>4.</b> Install additional apps with Flatpak</p>
        </div>
        </div>
        
        <p style="color: #7f8c8d; font-size: 14px;">
        If you have issues, contact the Kuns OS community.
        </p>
        </div>
        """)
        finish_text.setWordWrap(True)
        finish_text.setAlignment(Qt.AlignCenter)
        layout.addWidget(finish_text)
        
        restart_btn = QPushButton("Restart Now")
        restart_btn.setStyleSheet("font-size: 16px; padding: 15px 30px; background-color: #27ae60;")
        restart_btn.clicked.connect(self.restart_system)
        layout.addWidget(restart_btn, alignment=Qt.AlignCenter)
        
        layout.addStretch()
        
        return page
    
    def create_buttons(self, layout):
        btn_layout = QHBoxLayout()
        
        self.prev_btn = QPushButton("Previous")
        self.prev_btn.clicked.connect(self.prev_page)
        self.prev_btn.setEnabled(False)
        
        self.next_btn = QPushButton("Next")
        self.next_btn.clicked.connect(self.next_page)
        
        self.install_btn = QPushButton("Start Kuns OS Installation")
        self.install_btn.clicked.connect(self.start_install)
        self.install_btn.setVisible(False)
        
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.close)
        
        btn_layout.addWidget(self.cancel_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(self.prev_btn)
        btn_layout.addWidget(self.next_btn)
        btn_layout.addWidget(self.install_btn)
        
        layout.addLayout(btn_layout)
    
    def apply_styles(self):
        self.setStyleSheet("""
            QMainWindow {
                background-color: #ecf0f1;
            }
            
            QWidget {
                background-color: #ecf0f1;
                color: #2c3e50;
            }
            
            QPushButton {
                background-color: #3498db;
                color: white;
                border: none;
                padding: 10px 20px;
                font-size: 14px;
                border-radius: 5px;
                font-weight: bold;
            }
            
            QPushButton:hover {
                background-color: #2980b9;
            }
            
            QPushButton:pressed {
                background-color: #21618c;
            }
            
            QPushButton:disabled {
                background-color: #bdc3c7;
                color: #7f8c8d;
            }
            
            QLineEdit, QComboBox {
                background-color: white;
                border: 2px solid #bdc3c7;
                padding: 8px;
                border-radius: 4px;
                font-size: 14px;
            }
            
            QLineEdit:focus, QComboBox:focus {
                border-color: #3498db;
            }
            
            QGroupBox {
                font-weight: bold;
                border: 2px solid #bdc3c7;
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 10px;
            }
            
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
            }
            
            QProgressBar {
                border: 2px solid #bdc3c7;
                border-radius: 5px;
                text-align: center;
                font-weight: bold;
            }
            
            QProgressBar::chunk {
                background-color: #27ae60;
                border-radius: 3px;
            }
            
            QTableWidget {
                background-color: white;
                alternate-background-color: #f8f9fa;
                border: 1px solid #bdc3c7;
                border-radius: 4px;
            }
            
            QTableWidget::item {
                padding: 8px;
            }
            
            QTextEdit {
                background-color: #2c3e50;
                color: #ecf0f1;
                border: 1px solid #34495e;
                border-radius: 4px;
                font-family: 'Consolas', 'Monaco', monospace;
            }
            
            QCheckBox {
                spacing: 10px;
            }
            
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
            }
            
            QCheckBox::indicator:unchecked {
                border: 2px solid #bdc3c7;
                background-color: white;
                border-radius: 3px;
            }
            
            QCheckBox::indicator:checked {
                border: 2px solid #27ae60;
                background-color: #27ae60;
                border-radius: 3px;
            }
            
            QRadioButton::indicator {
                width: 18px;
                height: 18px;
                border-radius: 9px;
            }
            
            QRadioButton::indicator:unchecked {
                border: 2px solid #bdc3c7;
                background-color: white;
            }
            
            QRadioButton::indicator:checked {
                border: 2px solid #3498db;
                background-color: #3498db;
            }
        """)
    
    def next_page(self):
        if self.current_page == 1:  # Disk selection page
            if not self.disk_page.validate_selection():
                return
        elif self.current_page == 2:  # User settings page
            if not self.user_page.validate():
                return
        
        if self.current_page < 3:
            self.current_page += 1
            self.update_page()
    
    def prev_page(self):
        if self.current_page > 0:
            self.current_page -= 1
            self.update_page()
    
    def update_page(self):
        self.stack.setCurrentIndex(self.current_page)
        
        self.prev_btn.setEnabled(self.current_page > 0)
        self.next_btn.setVisible(self.current_page < 3)
        self.install_btn.setVisible(self.current_page == 3)
        
        if self.current_page == 4:  # Installation page
            self.prev_btn.setEnabled(False)
            self.cancel_btn.setText("Cancel Installation")
        elif self.current_page == 5:  # Completion page
            self.prev_btn.setVisible(False)
            self.next_btn.setVisible(False)
            self.install_btn.setVisible(False)
            self.cancel_btn.setText("Close")
    
    def start_install(self):
        # Check settings
        if not self.disk_page.validate_selection():
            return
        
        disk = self.disk_page.get_selected_disk()
        
        user_config = self.user_page.get_config()
        packages = self.package_page.get_packages()
        
        install_type = "Full Installation" if self.package_page.install_radio_full.isChecked() else "Minimal Installation"
        
        # Confirmation dialog
        reply = QMessageBox.question(
            self, "Kuns OS Installation Confirmation",
            f"Would you like to start Kuns OS installation with the following settings?\n\n"
            f"Disk: {disk}\n"
            f"User: {user_config['username']}\n"
            f"Hostname: {user_config['hostname']}\n"
            f"Installation Type: {install_type}\n"
            f"Packages: {len(packages)} packages\n\n"
            f"WARNING: All data on {disk} will be deleted!",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply != QMessageBox.Yes:
            return
        
        # Create installation configuration (Kuns OS specific)
        config = {
            "disk": disk,
            "hostname": user_config['hostname'],
            "username": user_config['username'],
            "password": user_config['password'],
            "root_password": user_config['root_password'],
            "keymap": user_config['keyboard'],
            "timezone": user_config['timezone'],
            "locale": "en_US.UTF-8",
            "packages": packages
        }
        
        # Start installation
        self.current_page = 4
        self.update_page()
        
        self.install_thread = ArchInstallThread(config)
        self.install_thread.progress.connect(self.progress_page.update_progress)
        self.install_thread.status.connect(self.progress_page.update_status)
        self.install_thread.log_output.connect(self.progress_page.add_log)
        self.install_thread.finished.connect(self.install_finished)
        
        self.install_thread.start()
    
    def install_finished(self, success, message):
        if success:
            self.current_page = 5
            self.update_page()
        else:
            QMessageBox.critical(self, "Installation Failed", message)
            self.current_page = 3  # Return to package selection page
            self.update_page()
    
    def restart_system(self):
        reply = QMessageBox.question(
            self, "Restart Confirmation",
            "Would you like to restart now to start Kuns OS?",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            subprocess.run(['reboot'])
    
    def closeEvent(self, event):
        if hasattr(self, 'install_thread') and self.install_thread and self.install_thread.isRunning():
            reply = QMessageBox.question(
                self, "Cancel Installation",
                "Kuns OS installation is in progress. Are you sure you want to cancel?",
                QMessageBox.Yes | QMessageBox.No
            )
            
            if reply == QMessageBox.Yes:
                self.install_thread.terminate()
                self.install_thread.wait()
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()

def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Kuns OS Installer")
    app.setOrganizationName("Kuns OS")
    
    # Check root privileges
    if os.geteuid() != 0:
        QMessageBox.critical(None, "Permission Error", 
                           "Kuns OS installer requires administrator privileges.\n\n"
                           "Please run with 'sudo kuns-installer' from terminal\n"
                           "or login as administrator.")
        sys.exit(1)
    
    # Check required tools availability
    required_tools = ['parted', 'mkfs.fat', 'mkfs.ext4', 'mount', 'pacstrap', 'genfstab', 'arch-chroot']
    missing_tools = []
    
    for tool in required_tools:
        try:
            subprocess.run(['which', tool], capture_output=True, check=True)
        except subprocess.CalledProcessError:
            missing_tools.append(tool)
    
    if missing_tools:
        QMessageBox.critical(None, "Dependency Error",
                           f"Required tools are missing: {', '.join(missing_tools)}\n\n"
                           "Please make sure you're running on Arch Linux installation media\n"
                           "with arch-install-scripts package installed.")
        sys.exit(1)
    
    installer = KunsInstaller()
    installer.show()
    
    sys.exit(app.exec_())

if __name__ == '__main__':
    main() 
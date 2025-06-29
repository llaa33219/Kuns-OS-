#!/bin/bash

# Kuns OS Default Wallpaper Setup Script
# Enhanced version to handle timing issues properly
set -e

LOG_FILE="$HOME/.wallpaper-setup.log"
LOCKFILE="$HOME/.wallpaper-setup.lock"

# Enhanced logging function
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

# Cleanup function
cleanup() {
    log "Cleanup: Removing lock file"
    rm -f "$LOCKFILE"
}
trap cleanup EXIT

# Check if already running
if [[ -f "$LOCKFILE" ]]; then
    log "Script already running, exiting"
    exit 0
fi

# Create lock file
echo $$ > "$LOCKFILE"

log "=== Kuns OS Wallpaper Setup Started ==="
log "Process ID: $$"
log "User: $(whoami)"
log "Display: ${DISPLAY:-none}"

# Function to check if Enlightenment is ready
wait_for_enlightenment() {
    log "Waiting for Enlightenment to be ready..."
    local max_attempts=60  # 60 seconds maximum
    local attempt=0
    
    while [[ $attempt -lt $max_attempts ]]; do
        # Check if enlightenment_remote is available
        if command -v enlightenment_remote >/dev/null 2>&1; then
            # Try to get current config (test if E is responding)
            if enlightenment_remote -desktop-bg-list >/dev/null 2>&1; then
                log "Enlightenment is ready and responding"
                return 0
            fi
        fi
        
        log "Attempt $((attempt+1))/$max_attempts: Enlightenment not ready yet"
        sleep 1
        ((attempt++))
    done
    
    log "ERROR: Enlightenment failed to become ready after $max_attempts seconds"
    return 1
}

# Function to set wallpaper using multiple methods
set_wallpaper() {
    local wallpaper_file="$1"
    local success=false
    
    log "Attempting to set wallpaper: $wallpaper_file"
    
    if [[ ! -f "$wallpaper_file" ]]; then
        log "ERROR: Wallpaper file not found: $wallpaper_file"
        return 1
    fi
    
    # Method 1: Direct enlightenment_remote command (Elive Forums method)
    log "Method 1: Using enlightenment_remote -desktop-bg-set"
    if enlightenment_remote -desktop-bg-set "$wallpaper_file" 2>&1 | tee -a "$LOG_FILE"; then
        log "Method 1: SUCCESS - enlightenment_remote command executed"
        success=true
    else
        log "Method 1: FAILED - enlightenment_remote command failed"
    fi
    
    # Wait a moment and verify
    sleep 2
    
    # Method 2: Alternative method with zone specification
    if [[ "$success" != true ]]; then
        log "Method 2: Using enlightenment_remote with zone 0"
        if enlightenment_remote -desktop-bg-set "$wallpaper_file" 0 2>&1 | tee -a "$LOG_FILE"; then
            log "Method 2: SUCCESS - enlightenment_remote with zone"
            success=true
        else
            log "Method 2: FAILED - enlightenment_remote with zone failed"
        fi
    fi
    
    # Method 3: Force config reload
    if [[ "$success" != true ]]; then
        log "Method 3: Forcing config reload"
        if enlightenment_remote -restart 2>&1 | tee -a "$LOG_FILE"; then
            log "Method 3: Enlightenment restart triggered"
            sleep 3
            if enlightenment_remote -desktop-bg-set "$wallpaper_file" 2>&1 | tee -a "$LOG_FILE"; then
                log "Method 3: SUCCESS - wallpaper set after restart"
                success=true
            fi
        fi
    fi
    
    return $([[ "$success" == true ]] && echo 0 || echo 1)
}

# Main execution
main() {
    log "Starting wallpaper setup process"
    
    # Wait for Enlightenment to be ready
    if ! wait_for_enlightenment; then
        log "FATAL: Enlightenment is not ready, aborting"
        exit 1
    fi
    
    # Give extra time for full initialization
    log "Giving Enlightenment extra time to fully initialize..."
    sleep 5
    
    # Define wallpaper search paths in priority order
    local wallpaper_paths=(
        "$HOME/.e/e/backgrounds/default-wallpaper.edj"
        "$HOME/.e/e/backgrounds/default-wallpaper.png"
        "$HOME/.e/e/backgrounds/background-image.png"
        "/usr/share/backgrounds/default-wallpaper.png"
        "/usr/share/backgrounds/background-image.png"
        "/usr/share/enlightenment/data/backgrounds/default-wallpaper.edj"
    )
    
    # Try each wallpaper file
    local wallpaper_set=false
    for wallpaper in "${wallpaper_paths[@]}"; do
        if [[ -f "$wallpaper" ]]; then
            log "Found wallpaper: $wallpaper"
            if set_wallpaper "$wallpaper"; then
                log "SUCCESS: Wallpaper set successfully to: $wallpaper"
                wallpaper_set=true
                break
            else
                log "FAILED: Could not set wallpaper: $wallpaper"
            fi
        else
            log "Wallpaper not found: $wallpaper"
        fi
    done
    
    if [[ "$wallpaper_set" != true ]]; then
        log "ERROR: Failed to set any wallpaper"
        exit 1
    fi
    
    # Final verification
    log "Performing final verification..."
    sleep 2
    
    # Try to query current background (if command exists)
    if enlightenment_remote -desktop-bg-list >/dev/null 2>&1; then
        log "Current background list:"
        enlightenment_remote -desktop-bg-list 2>&1 | tee -a "$LOG_FILE"
    fi
    
    log "=== Wallpaper setup completed successfully ==="
}

# Delayed execution to ensure proper timing
log "Scheduling wallpaper setup with delay..."
sleep 10  # Initial delay to let Enlightenment fully start

# Run main function
main

log "=== Script execution finished ===" 
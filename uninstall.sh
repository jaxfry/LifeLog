#!/usr/bin/env bash

# LifeLog Daemon Uninstaller
# Clean removal of LifeLog daemon and configuration

set -euo pipefail

# Colors and styling
readonly RED='\033[0;31m'
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[1;33m'
readonly BLUE='\033[0;34m'
readonly CYAN='\033[0;36m'
readonly WHITE='\033[1;37m'
readonly BOLD='\033[1m'
readonly DIM='\033[2m'
readonly NC='\033[0m' # No Color

# Configuration
readonly LIFELOG_DIR="$HOME/.lifelog"
readonly SERVICE_NAME="lifelog-daemon"

print_banner() {
    clear
    echo -e "${RED}${BOLD}"
    cat << 'EOF'
╭─────────────────────────────────────────────────────────────────╮
│                                                                 │
│  ██╗     ██╗███████╗███████╗██╗      ██████╗  ██████╗           │
│  ██║     ██║██╔════╝██╔════╝██║     ██╔═══██╗██╔════╝           │
│  ██║     ██║█████╗  █████╗  ██║     ██║   ██║██║  ███╗          │
│  ██║     ██║██╔══╝  ██╔══╝  ██║     ██║   ██║██║   ██║          │
│  ███████╗██║██║     ███████╗███████╗╚██████╔╝╚██████╔╝          │
│  ╚══════╝╚═╝╚═╝     ╚══════╝╚══════╝ ╚═════╝  ╚═════╝           │
│                                                                 │
│                        🗑️  UNINSTALLER                          │
│                                                                 │
╰─────────────────────────────────────────────────────────────────╯
EOF
    echo -e "${NC}"
    echo -e "${WHITE}${BOLD}LifeLog Daemon Uninstaller${NC}"
    echo -e "${DIM}This will remove LifeLog daemon from your system${NC}"
    echo ""
}

print_step() {
    echo -e "${BLUE}${BOLD}▶${NC} ${WHITE}$1${NC}"
}

print_success() {
    echo -e "${GREEN}${BOLD}✓${NC} ${GREEN}$1${NC}"
}

print_warning() {
    echo -e "${YELLOW}${BOLD}⚠${NC} ${YELLOW}$1${NC}"
}

print_error() {
    echo -e "${RED}${BOLD}✗${NC} ${RED}$1${NC}"
}

prompt_yes_no() {
    local prompt="$1"
    local default="$2"
    
    while true; do
        if [[ "$default" == "y" ]]; then
            read -p "$prompt [Y/n]: " result
            result=${result:-y}
        else
            read -p "$prompt [y/N]: " result
            result=${result:-n}
        fi
        
        case $result in
            [Yy]* ) return 0;;
            [Nn]* ) return 1;;
            * ) echo -e "${RED}Please answer yes or no.${NC}";;
        esac
    done
}

detect_os() {
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        echo "linux"
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        echo "macos"
    else
        echo "unknown"
    fi
}

stop_daemon() {
    print_step "Stopping LifeLog daemon..."
    
    local os_type
    os_type=$(detect_os)
    
    case "$os_type" in
        "linux")
            if systemctl --user is-active --quiet lifelog-daemon.service 2>/dev/null; then
                systemctl --user stop lifelog-daemon.service 2>/dev/null || true
                systemctl --user disable lifelog-daemon.service 2>/dev/null || true
                print_success "Systemd service stopped and disabled"
            fi
            ;;
        "macos")
            local plist_file="$HOME/Library/LaunchAgents/com.lifelog.daemon.plist"
            if [[ -f "$plist_file" ]]; then
                launchctl unload "$plist_file" 2>/dev/null || true
                print_success "Launch Agent unloaded"
            fi
            ;;
    esac
    
    # Kill any running daemon processes
    if pgrep -f "lifelog.*daemon" > /dev/null; then
        pkill -f "lifelog.*daemon" || true
        sleep 2
        print_success "Daemon processes terminated"
    fi
}

remove_services() {
    print_step "Removing service files..."
    
    local os_type
    os_type=$(detect_os)
    
    case "$os_type" in
        "linux")
            local service_file="$HOME/.config/systemd/user/lifelog-daemon.service"
            if [[ -f "$service_file" ]]; then
                rm -f "$service_file"
                systemctl --user daemon-reload 2>/dev/null || true
                print_success "Systemd service file removed"
            fi
            ;;
        "macos")
            local plist_file="$HOME/Library/LaunchAgents/com.lifelog.daemon.plist"
            if [[ -f "$plist_file" ]]; then
                rm -f "$plist_file"
                print_success "Launch Agent plist removed"
            fi
            ;;
    esac
}

remove_files() {
    print_step "Removing LifeLog files..."
    
    # Remove main directory
    if [[ -d "$LIFELOG_DIR" ]]; then
        rm -rf "$LIFELOG_DIR"
        print_success "LifeLog directory removed: $LIFELOG_DIR"
    fi
    
    # Remove symlinks
    if [[ -L "$HOME/.local/bin/lifelog-daemon" ]]; then
        rm -f "$HOME/.local/bin/lifelog-daemon"
        print_success "Symlink removed from ~/.local/bin"
    fi
    
    # Remove from PATH alternatives
    local common_paths=("/usr/local/bin" "/opt/local/bin")
    for path in "${common_paths[@]}"; do
        if [[ -L "$path/lifelog-daemon" ]]; then
            sudo rm -f "$path/lifelog-daemon" 2>/dev/null || true
        fi
    done
}

show_summary() {
    local items_found=0
    
    echo -e "${WHITE}${BOLD}Found LifeLog components:${NC}"
    echo ""
    
    # Check directory
    if [[ -d "$LIFELOG_DIR" ]]; then
        echo -e "${YELLOW}📁 Installation directory: $LIFELOG_DIR${NC}"
        if [[ -f "$LIFELOG_DIR/config.env" ]]; then
            echo -e "${DIM}   └── Configuration file${NC}"
        fi
        if [[ -d "$LIFELOG_DIR/daemon" ]]; then
            echo -e "${DIM}   └── Daemon files${NC}"
        fi
        if [[ -f "$LIFELOG_DIR/daemon.log" ]]; then
            echo -e "${DIM}   └── Log files${NC}"
        fi
        items_found=$((items_found + 1))
    fi
    
    # Check services
    local os_type
    os_type=$(detect_os)
    
    case "$os_type" in
        "linux")
            if [[ -f "$HOME/.config/systemd/user/lifelog-daemon.service" ]]; then
                echo -e "${YELLOW}🔧 Systemd service${NC}"
                items_found=$((items_found + 1))
            fi
            ;;
        "macos")
            if [[ -f "$HOME/Library/LaunchAgents/com.lifelog.daemon.plist" ]]; then
                echo -e "${YELLOW}🔧 Launch Agent${NC}"
                items_found=$((items_found + 1))
            fi
            ;;
    esac
    
    # Check running processes
    if pgrep -f "lifelog.*daemon" > /dev/null; then
        echo -e "${YELLOW}🏃 Running daemon process${NC}"
        items_found=$((items_found + 1))
    fi
    
    # Check symlinks
    if [[ -L "$HOME/.local/bin/lifelog-daemon" ]]; then
        echo -e "${YELLOW}🔗 Symlink in ~/.local/bin${NC}"
        items_found=$((items_found + 1))
    fi
    
    echo ""
    
    if [[ $items_found -eq 0 ]]; then
        echo -e "${GREEN}✓ No LifeLog components found${NC}"
        echo -e "${DIM}LifeLog appears to already be uninstalled.${NC}"
        return 1
    fi
    
    return 0
}

main() {
    print_banner
    
    # Check what's installed
    if ! show_summary; then
        exit 0
    fi
    
    echo -e "${RED}${BOLD}⚠️  This will completely remove LifeLog from your system ⚠️${NC}"
    echo -e "${DIM}This action cannot be undone.${NC}"
    echo ""
    
    # Confirmation
    if ! prompt_yes_no "Are you sure you want to uninstall LifeLog?" "n"; then
        echo -e "${YELLOW}Uninstallation cancelled.${NC}"
        exit 0
    fi
    
    echo ""
    print_step "Starting uninstallation..."
    
    # Uninstallation steps
    stop_daemon
    remove_services
    remove_files
    
    echo ""
    print_success "LifeLog has been completely removed from your system"
    echo ""
    
    echo -e "${WHITE}${BOLD}What was removed:${NC}"
    echo -e "${GREEN}✓${NC} All daemon files and directories"
    echo -e "${GREEN}✓${NC} Configuration files"
    echo -e "${GREEN}✓${NC} Log files and cache"
    echo -e "${GREEN}✓${NC} System services (systemd/launchd)"
    echo -e "${GREEN}✓${NC} Launcher scripts and symlinks"
    echo ""
    
    echo -e "${CYAN}${BOLD}Note:${NC} ${CYAN}ActivityWatch was not removed (if installed separately)${NC}"
    echo -e "${CYAN}Python packages installed by LifeLog remain installed${NC}"
    echo ""
    
    echo -e "${WHITE}Thank you for using LifeLog! 👋${NC}"
}

# Run the uninstaller
main "$@"

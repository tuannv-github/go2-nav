#!/bin/bash

# =============================================================================
# Reverse SSH Service Installation Script
# =============================================================================

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
SERVICE_NAME="reverse-ssh"
SERVICE_FILE="reverse-ssh.service"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_PATH="/etc/systemd/system/${SERVICE_FILE}"

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to check if running as root
check_root() {
    if [[ $EUID -ne 0 ]]; then
        print_error "This script must be run as root (use sudo)"
        exit 1
    fi
}

# Function to check prerequisites
check_prerequisites() {
    print_status "Checking prerequisites..."
    
    # Check if the reverse_ssh.sh script exists
    if [[ ! -f "$SCRIPT_DIR/reverse_ssh.sh" ]]; then
        print_error "reverse_ssh.sh script not found: $SCRIPT_DIR/reverse_ssh.sh"
        exit 1
    fi
    
    # Check if common.sh exists
    if [[ ! -f "$SCRIPT_DIR/common.sh" ]]; then
        print_error "common.sh script not found: $SCRIPT_DIR/common.sh"
        exit 1
    fi
    
    # Check if the service file exists
    if [[ ! -f "$SCRIPT_DIR/$SERVICE_FILE" ]]; then
        print_error "Service file not found: $SCRIPT_DIR/$SERVICE_FILE"
        exit 1
    fi
    
    # Check if systemd is available
    if ! command -v systemctl &> /dev/null; then
        print_error "systemd is not available. This script requires systemd."
        exit 1
    fi
    
    # Check if SSH key exists
    SSH_KEY="$HOME/.ssh/id_rsa_unitree_robot"
    if [[ ! -f "$SSH_KEY" ]] && [[ ! -f "/home/unitree/.ssh/id_rsa_unitree_robot" ]]; then
        print_warning "SSH key not found at ~/.ssh/id_rsa_unitree_robot"
        print_warning "The service may fail to connect. Please ensure the SSH key is configured."
    fi
    
    print_success "All prerequisites met"
}

# Function to install the service
install_service() {
    print_status "Installing systemd service..."
    
    # Copy service file to systemd directory
    cp "$SCRIPT_DIR/$SERVICE_FILE" "$SERVICE_PATH"
    
    # Ensure the script is executable
    chmod +x "$SCRIPT_DIR/reverse_ssh.sh"
    
    # Reload systemd to recognize the new service
    systemctl daemon-reload
    
    # Enable the service to start on boot
    systemctl enable "$SERVICE_NAME"
    
    # Verify the service is enabled
    if systemctl is-enabled --quiet "$SERVICE_NAME"; then
        print_success "Service installed and enabled for automatic startup on boot"
    else
        print_error "Failed to enable service for automatic startup"
        exit 1
    fi
}

# Function to start the service
start_service() {
    print_status "Starting service..."
    
    # Start the service
    systemctl start "$SERVICE_NAME"
    
    # Wait a moment for the service to start
    sleep 2
    
    # Check if the service is running
    if systemctl is-active --quiet "$SERVICE_NAME"; then
        print_success "Service started successfully"
    else
        print_error "Failed to start service"
        print_status "Checking service status..."
        systemctl status "$SERVICE_NAME" --no-pager
        exit 1
    fi
}

# Function to show service status
show_status() {
    print_status "Service status:"
    systemctl status "$SERVICE_NAME" --no-pager
    
    echo ""
    print_status "Service logs (last 20 lines):"
    journalctl -u "$SERVICE_NAME" --no-pager -n 20
}

# Function to show usage information
show_usage() {
    echo ""
    print_status "Service management commands:"
    echo "  sudo systemctl start $SERVICE_NAME     # Start the service"
    echo "  sudo systemctl stop $SERVICE_NAME      # Stop the service"
    echo "  sudo systemctl restart $SERVICE_NAME   # Restart the service"
    echo "  sudo systemctl status $SERVICE_NAME    # Check service status"
    echo "  sudo systemctl enable $SERVICE_NAME    # Enable service on boot (already enabled)"
    echo "  sudo systemctl disable $SERVICE_NAME   # Disable service on boot"
    echo ""
    print_status "Logging commands:"
    echo "  journalctl -u $SERVICE_NAME -f         # Follow service logs"
    echo "  journalctl -u $SERVICE_NAME --since today  # Show today's logs"
    echo ""
    print_status "Configuration file: $SERVICE_PATH"
    print_status "Service will start automatically on boot"
}

# Function to uninstall the service
uninstall_service() {
    print_status "Uninstalling service..."
    
    # Stop the service if it's running
    if systemctl is-active --quiet "$SERVICE_NAME"; then
        systemctl stop "$SERVICE_NAME"
    fi
    
    # Disable the service
    systemctl disable "$SERVICE_NAME"
    
    # Remove the service file
    rm -f "$SERVICE_PATH"
    
    # Reload systemd
    systemctl daemon-reload
    
    print_success "Service uninstalled"
}

# Main installation function
main() {
    echo "============================================================================="
    echo "Reverse SSH Service Installation Script"
    echo "============================================================================="
    echo ""
    
    check_root
    check_prerequisites
    install_service
    start_service
    show_status
    show_usage
    
    echo ""
    print_success "Installation completed successfully!"
    print_status "The reverse SSH service is now running and will start automatically on boot."
    
    # Show enabled status
    if systemctl is-enabled --quiet "$SERVICE_NAME"; then
        print_success "✓ Service is enabled for automatic startup on boot"
    else
        print_warning "⚠ Service is not enabled for automatic startup"
    fi
    
    # Show current status
    if systemctl is-active --quiet "$SERVICE_NAME"; then
        print_success "✓ Service is currently running"
    else
        print_warning "⚠ Service is not currently running"
    fi
}

# Handle command line arguments
case "${1:-install}" in
    install)
        main
        ;;
    uninstall)
        check_root
        uninstall_service
        print_success "Service uninstalled successfully!"
        ;;
    status)
        show_status
        ;;
    *)
        echo "Usage: $0 [install|uninstall|status]"
        echo ""
        echo "  install   - Install and start the service (default)"
        echo "  uninstall - Remove the service"
        echo "  status    - Show service status and logs"
        echo ""
        echo "Examples:"
        echo "  sudo ./install_service.sh           # Install and start service"
        echo "  sudo ./install_service.sh uninstall # Remove service"
        echo "  ./install_service.sh status         # Check service status"
        exit 1
        ;;
esac

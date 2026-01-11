#!/bin/bash
# Script to save/backup RTAB-Map database

readonly SAVE_RTABMAP_SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Default values
RTABMAP_NODE_NAME="${RTABMAP_NODE_NAME:-rtabmap}"
BACKUP_DIR="${BACKUP_DIR:-$HOME/.ros/rtabmap_backups}"
DATABASE_PATH="${DATABASE_PATH:-$HOME/.ros/rtabmap.db}"

# Parse arguments
SAVE_METHOD="backup"  # 'backup' (via service) or 'copy' (direct file copy)
OUTPUT_PATH=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --method)
            SAVE_METHOD="$2"
            shift 2
            ;;
        --output|-o)
            OUTPUT_PATH="$2"
            shift 2
            ;;
        --node-name)
            RTABMAP_NODE_NAME="$2"
            shift 2
            ;;
        --database-path)
            DATABASE_PATH="$2"
            shift 2
            ;;
        --help|-h)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Save or backup RTAB-Map database"
            echo ""
            echo "Options:"
            echo "  --method METHOD      Save method: 'backup' (via ROS service) or 'copy' (direct copy). Default: backup"
            echo "  --output PATH        Output path for saved map (for copy method). Default: timestamped backup"
            echo "  --node-name NAME     RTAB-Map node name. Default: rtabmap"
            echo "  --database-path PATH Path to RTAB-Map database. Default: ~/.ros/rtabmap.db"
            echo "  --help, -h           Show this help message"
            echo ""
            echo "Examples:"
            echo "  $0                                    # Backup using ROS service"
            echo "  $0 --method copy --output map.db      # Copy database to map.db"
            echo "  $0 --method backup                    # Force backup via service"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

if [ "$SAVE_METHOD" = "backup" ]; then
    # Use ROS2 service to backup the database
    echo "Calling RTAB-Map backup service..."
    if ros2 service call /${RTABMAP_NODE_NAME}/backup std_srvs/srv/Empty; then
        echo "✓ RTAB-Map database backed up successfully!"
        echo "  Backup location: ${DATABASE_PATH}.back"
    else
        echo "✗ Failed to call backup service. Is RTAB-Map running?"
        echo "  Trying direct copy method instead..."
        SAVE_METHOD="copy"
    fi
fi

if [ "$SAVE_METHOD" = "copy" ]; then
    # Direct file copy
    if [ ! -f "$DATABASE_PATH" ]; then
        echo "✗ Database file not found: $DATABASE_PATH"
        exit 1
    fi
    
    if [ -z "$OUTPUT_PATH" ]; then
        # Create backup directory if it doesn't exist
        mkdir -p "$BACKUP_DIR"
        
        # Generate timestamped backup filename
        TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
        OUTPUT_PATH="${BACKUP_DIR}/rtabmap_${TIMESTAMP}.db"
    fi
    
    echo "Copying database..."
    if cp "$DATABASE_PATH" "$OUTPUT_PATH"; then
        FILE_SIZE=$(du -h "$OUTPUT_PATH" | cut -f1)
        echo "✓ RTAB-Map database saved successfully!"
        echo "  Source: $DATABASE_PATH"
        echo "  Destination: $OUTPUT_PATH"
        echo "  Size: $FILE_SIZE"
    else
        echo "✗ Failed to copy database file"
        exit 1
    fi
fi

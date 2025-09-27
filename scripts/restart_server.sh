#!/bin/bash

# Simple restart script - stops then starts all MPC servers

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Restarting MPC servers..."

# Stop all servers
echo "Stopping servers..."
"$SCRIPT_DIR/stop_servers.sh"

# Wait a moment for cleanup
sleep 2

# Start all servers
echo "Starting servers..."
"$SCRIPT_DIR/start_servers.sh"

echo "Restart complete!"
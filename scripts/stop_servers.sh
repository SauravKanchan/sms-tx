#!/bin/bash

# MPC Signature Server Stop Script
# This script stops all MPC signature server instances

echo "Stopping MPC Signature Server instances..."

# Kill tmux sessions
if tmux has-session -t mpc-server-1 2>/dev/null; then
    echo "Stopping MPC Server 1..."
    tmux kill-session -t mpc-server-1
fi

if tmux has-session -t mpc-server-2 2>/dev/null; then
    echo "Stopping MPC Server 2..."
    tmux kill-session -t mpc-server-2
fi

if tmux has-session -t mpc-server-3 2>/dev/null; then
    echo "Stopping MPC Server 3..."
    tmux kill-session -t mpc-server-3
fi

# Also kill any Python processes running the server (fallback)
pkill -f "python server.py" 2>/dev/null || true

echo ""
echo "✅ All MPC servers stopped successfully!"
echo ""
echo "To restart the servers, run: ./scripts/start_servers.sh"
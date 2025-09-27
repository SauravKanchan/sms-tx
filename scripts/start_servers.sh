#!/bin/bash

# MPC Signature Server Startup Script
# This script starts 3 MPC signature server instances in tmux sessions

set -e

# Check if tmux is installed
if ! command -v tmux &> /dev/null; then
    echo "Error: tmux is not installed. Please install tmux first."
    exit 1
fi

# Check if config.json exists
if [ ! -f "config.json" ]; then
    echo "Error: config.json not found. Please ensure it exists in the project root."
    exit 1
fi

# Check if .env file exists
if [ ! -f ".env" ]; then
    echo "Error: .env file not found. Please copy .env.example to .env and set your configuration:"
    echo "  cp .env.example .env"
    echo "  # Edit .env and set FAUCET_PRIVATE_KEY=YourActualPrivateKey"
    exit 1
fi

# Load environment variables
set -a
source .env
set +a

# Validate required environment variables
if [ -z "$FAUCET_PRIVATE_KEY" ]; then
    echo "Error: FAUCET_PRIVATE_KEY not set in .env file"
    echo "Please edit .env and set: FAUCET_PRIVATE_KEY=YourActualPrivateKey"
    exit 1
fi

# Check if faucet private key is the placeholder
if [ "$FAUCET_PRIVATE_KEY" = "0x0000000000000000000000000000000000000000000000000000000000000001" ]; then
    echo "Warning: FAUCET_PRIVATE_KEY is set to the placeholder value."
    echo "For production use, please set a real private key in .env file."
    echo "Continuing with placeholder key for development..."
fi

# Check if Python environment is activated
if [ -z "$VIRTUAL_ENV" ]; then
    echo "Warning: No virtual environment detected. Activating .venv..."
    if [ -d ".venv" ]; then
        source .venv/bin/activate
        echo "Virtual environment activated."
    else
        echo "Error: No .venv directory found. Please create and activate a virtual environment first."
        exit 1
    fi
fi

# Check if required packages are installed
python -c "import flask, sqlalchemy, web3, coincurve" 2>/dev/null || {
    echo "Error: Required packages not installed. Run: pip install -r requirements.txt"
    exit 1
}

echo "Starting MPC Signature Server instances..."

# Kill existing sessions if they exist
tmux has-session -t mpc-server-1 2>/dev/null && tmux kill-session -t mpc-server-1
tmux has-session -t mpc-server-2 2>/dev/null && tmux kill-session -t mpc-server-2  
tmux has-session -t mpc-server-3 2>/dev/null && tmux kill-session -t mpc-server-3

# Start server 1 (participant ID 1, API port 3001)
echo "Starting MPC Server 1 (Participant 1) on port 3001..."
tmux new-session -d -s mpc-server-1 "python server.py --participant-id 1; read"

# Start server 2 (participant ID 2, API port 3002)
echo "Starting MPC Server 2 (Participant 2) on port 3002..."
tmux new-session -d -s mpc-server-2 "python server.py --participant-id 2; read"

# Start server 3 (participant ID 3, API port 3003)
echo "Starting MPC Server 3 (Participant 3) on port 3003..."
tmux new-session -d -s mpc-server-3 "python server.py --participant-id 3; read"

# Wait a moment for servers to start
sleep 3

echo ""
echo "✅ All MPC servers started successfully!"
echo ""
echo "Server Status:"
echo "- Server 1: http://localhost:3001 (tmux session: mpc-server-1)"
echo "- Server 2: http://localhost:3002 (tmux session: mpc-server-2)" 
echo "- Server 3: http://localhost:3003 (tmux session: mpc-server-3)"
echo ""
echo "Commands:"
echo "  View logs:           tmux attach-session -t mpc-server-<1|2|3>"
echo "  Stop all servers:    ./scripts/stop_servers.sh"
echo "  Check status:        ./scripts/check_servers.sh"
echo ""
echo "Test the servers:"
echo "  curl http://localhost:3001/api/ping"
echo "  curl http://localhost:3002/api/ping"
echo "  curl http://localhost:3003/api/ping"
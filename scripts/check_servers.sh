#!/bin/bash

# MPC Signature Server Status Check Script
# This script checks the status of all MPC signature server instances

echo "Checking MPC Signature Server status..."
echo ""

# Function to check if a tmux session is running
check_tmux_session() {
    local session_name=$1
    if tmux has-session -t "$session_name" 2>/dev/null; then
        echo "✅ tmux session '$session_name' is running"
        return 0
    else
        echo "❌ tmux session '$session_name' is not running"
        return 1
    fi
}

# Function to check if server is responding
check_server_api() {
    local port=$1
    local participant=$2
    local url="http://localhost:$port/api/ping"
    
    if curl -s --connect-timeout 5 "$url" >/dev/null 2>&1; then
        echo "✅ Server $participant API responding on port $port"
        # Get actual response
        response=$(curl -s "$url" 2>/dev/null)
        echo "   Response: $response"
        return 0
    else
        echo "❌ Server $participant API not responding on port $port"
        return 1
    fi
}

echo "Tmux Sessions:"
check_tmux_session "mpc-server-1"
check_tmux_session "mpc-server-2"
check_tmux_session "mpc-server-3"

echo ""
echo "API Endpoints:"
check_server_api "3001" "1"
check_server_api "3002" "2" 
check_server_api "3003" "3"

echo ""
echo "All tmux sessions:"
tmux list-sessions 2>/dev/null | grep "mpc-server" || echo "No MPC server tmux sessions found"

echo ""
echo "Process information:"
pgrep -f "python server.py" >/dev/null 2>&1 && {
    echo "Python server processes:"
    pgrep -fl "python server.py"
} || {
    echo "No Python server processes found"
}

echo ""
echo "Port usage:"
netstat -an 2>/dev/null | grep ":300[123] " || lsof -i :3001 -i :3002 -i :3003 2>/dev/null || echo "No processes listening on ports 3001-3003"
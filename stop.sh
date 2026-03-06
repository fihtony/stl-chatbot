#!/bin/bash

# Collège Saint-Louis Chatbot - Stop script
# Stops all running services

echo "🛑 Stopping Collège Saint-Louis Chatbot services..."

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Stop services from PID files
if [ -f "logs/backend.pid" ]; then
    BACKEND_PID=$(cat logs/backend.pid)
    if ps -p $BACKEND_PID > /dev/null 2>&1; then
        echo -e "${YELLOW}Stopping backend (PID: $BACKEND_PID)...${NC}"
        kill $BACKEND_PID 2>/dev/null || true
        sleep 1
        kill -9 $BACKEND_PID 2>/dev/null || true
    fi
    rm -f logs/backend.pid
fi

if [ -f "logs/frontend.pid" ]; then
    FRONTEND_PID=$(cat logs/frontend.pid)
    if ps -p $FRONTEND_PID > /dev/null 2>&1; then
        echo -e "${YELLOW}Stopping frontend (PID: $FRONTEND_PID)...${NC}"
        kill $FRONTEND_PID 2>/dev/null || true
        sleep 1
        kill -9 $FRONTEND_PID 2>/dev/null || true
    fi
    rm -f logs/frontend.pid
fi

# Clean up any remaining processes
echo -e "${YELLOW}Cleaning up remaining processes...${NC}"
pkill -f "api_server.py" 2>/dev/null || true
pkill -f "next dev" 2>/dev/null || true

echo -e "${GREEN}✅ All services stopped${NC}"

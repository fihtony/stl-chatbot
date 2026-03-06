#!/bin/bash

# Collège Saint-Louis Chatbot - Start script
# Starts both frontend and backend services

set -e

echo "🚀 Starting Collège Saint-Louis Chatbot..."
echo ""

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check Python
echo -e "${BLUE}📦 Checking Python...${NC}"
if ! command -v python3 &> /dev/null; then
    echo -e "${YELLOW}⚠️  Python 3 is not installed${NC}"
    exit 1
fi

# Check Node.js
echo -e "${BLUE}📦 Checking Node.js...${NC}"
if ! command -v node &> /dev/null; then
    echo -e "${YELLOW}⚠️  Node.js is not installed${NC}"
    exit 1
fi

# Check backend dependencies
echo -e "${BLUE}📦 Checking backend dependencies...${NC}"
cd backend
if [ ! -d "venv" ]; then
    echo -e "${YELLOW}⚠️  Virtual env not found, creating...${NC}"
    python3 -m venv venv
fi

source venv/bin/activate
pip install -q -r requirements.txt
cd ..

# Check frontend dependencies
echo -e "${BLUE}📦 Checking frontend dependencies...${NC}"
cd frontend
if [ ! -d "node_modules" ]; then
    echo -e "${YELLOW}⚠️  Node modules not found, installing...${NC}"
    npm install
fi
cd ..

# Log directory (absolute path from project root)
LOG_DIR="$(cd "$(dirname "$0")" && pwd)/logs"
mkdir -p "$LOG_DIR"
BACKEND_LOG="$LOG_DIR/backend.log"
FRONTEND_LOG="$LOG_DIR/frontend.log"

echo ""
echo -e "${GREEN}✅ Environment check complete${NC}"
echo ""

# Start backend: PYTHONUNBUFFERED=1 and python -u disable buffering; tee writes to file and terminal
echo -e "${BLUE}🐍 Starting Python backend (port 8086)...${NC}"
cd backend
source venv/bin/activate
: > "$BACKEND_LOG"
PYTHONUNBUFFERED=1 python -u api_server.py 2>&1 | tee "$BACKEND_LOG" &
BACKEND_PID=$!
cd ..

# Wait for backend: up to 60s, check /api/health every 2s
echo -e "${YELLOW}⏳ Waiting for backend to start...${NC}"
BACKEND_OK=0
for i in $(seq 1 30); do
    if curl -sf http://localhost:8086/api/health > /dev/null; then
        BACKEND_OK=1
        break
    fi
    sleep 2
done

if [ "$BACKEND_OK" -ne 1 ]; then
    echo -e "${YELLOW}⚠️  Backend failed to start. Last 40 lines of log:${NC}"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    tail -40 "$BACKEND_LOG" 2>/dev/null || echo "(no output)"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo -e "${YELLOW}Full log: $BACKEND_LOG${NC}"
    kill $BACKEND_PID 2>/dev/null || true
    exit 1
fi

echo -e "${GREEN}✅ Backend started (PID: $BACKEND_PID)${NC}"

# Start frontend (tee writes to log and terminal)
echo -e "${BLUE}⚛️  Starting Next.js frontend (port 3086)...${NC}"
cd frontend
: > "$FRONTEND_LOG"
npm run dev 2>&1 | tee "$FRONTEND_LOG" &
FRONTEND_PID=$!
cd ..

echo ""
echo -e "${GREEN}✅ All services started!${NC}"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo -e "${BLUE}📱 Frontend:${NC} http://localhost:3086"
echo -e "${BLUE}🔧 Backend:${NC} http://localhost:8086"
echo -e "${BLUE}📊 API docs:${NC} http://localhost:8086/docs"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo -e "${YELLOW}💡 Tips:${NC}"
echo "  - Press Ctrl+C to stop all services"
echo "  - View logs: tail -f $BACKEND_LOG or $FRONTEND_LOG"
echo ""

# Save PIDs
echo $BACKEND_PID > "$LOG_DIR/backend.pid"
echo $FRONTEND_PID > "$LOG_DIR/frontend.pid"

# Wait for user interrupt
trap "echo ''; echo '🛑 Stopping services...'; kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; rm -f \"$LOG_DIR\"/*.pid; echo '✅ All services stopped'; exit 0" INT TERM

# Keep script running
wait

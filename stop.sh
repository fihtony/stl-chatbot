#!/bin/bash

# Collège Saint-Louis Chatbot - 停止脚本
# 停止所有运行的服务

echo "🛑 停止 Collège Saint-Louis Chatbot 服务..."

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 从 PID 文件停止服务
if [ -f "logs/backend.pid" ]; then
    BACKEND_PID=$(cat logs/backend.pid)
    if ps -p $BACKEND_PID > /dev/null 2>&1; then
        echo -e "${YELLOW}停止后端服务 (PID: $BACKEND_PID)...${NC}"
        kill $BACKEND_PID 2>/dev/null || true
        sleep 1
        # 强制停止
        kill -9 $BACKEND_PID 2>/dev/null || true
    fi
    rm -f logs/backend.pid
fi

if [ -f "logs/frontend.pid" ]; then
    FRONTEND_PID=$(cat logs/frontend.pid)
    if ps -p $FRONTEND_PID > /dev/null 2>&1; then
        echo -e "${YELLOW}停止前端服务 (PID: $FRONTEND_PID)...${NC}"
        kill $FRONTEND_PID 2>/dev/null || true
        sleep 1
        # 强制停止
        kill -9 $FRONTEND_PID 2>/dev/null || true
    fi
    rm -f logs/frontend.pid
fi

# 额外清理:停止所有相关进程
echo -e "${YELLOW}清理残留进程...${NC}"
pkill -f "api_server.py" 2>/dev/null || true
pkill -f "next dev" 2>/dev/null || true

echo -e "${GREEN}✅ 所有服务已停止${NC}"

#!/bin/bash

# Collège Saint-Louis Chatbot - 启动脚本
# 同时启动前端和后端服务

set -e

echo "🚀 启动 Collège Saint-Louis Chatbot..."
echo ""

# 颜色定义
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 检查 Python 环境
echo -e "${BLUE}📦 检查 Python 环境...${NC}"
if ! command -v python3 &> /dev/null; then
    echo -e "${YELLOW}⚠️  Python 3 未安装${NC}"
    exit 1
fi

# 检查 Node.js 环境
echo -e "${BLUE}📦 检查 Node.js 环境...${NC}"
if ! command -v node &> /dev/null; then
    echo -e "${YELLOW}⚠️  Node.js 未安装${NC}"
    exit 1
fi

# 检查后端依赖
echo -e "${BLUE}📦 检查后端依赖...${NC}"
cd backend
if [ ! -d "venv" ]; then
    echo -e "${YELLOW}⚠️  虚拟环境不存在,正在创建...${NC}"
    python3 -m venv venv
fi

source venv/bin/activate
pip install -q -r requirements.txt
cd ..

# 检查前端依赖
echo -e "${BLUE}📦 检查前端依赖...${NC}"
cd frontend
if [ ! -d "node_modules" ]; then
    echo -e "${YELLOW}⚠️  Node 模块不存在,正在安装...${NC}"
    npm install
fi
cd ..

# 创建日志目录
mkdir -p logs

echo ""
echo -e "${GREEN}✅ 环境检查完成${NC}"
echo ""

# 启动后端
echo -e "${BLUE}🐍 启动 Python 后端 (端口 8086)...${NC}"
cd backend
source venv/bin/activate
python api_server.py > ../logs/backend.log 2>&1 &
BACKEND_PID=$!
cd ..

# 等待后端启动
echo -e "${YELLOW}⏳ 等待后端启动...${NC}"
sleep 3

# 检查后端是否启动成功
if ! curl -s http://localhost:8086/api/health > /dev/null; then
    echo -e "${YELLOW}⚠️  后端启动失败,请检查日志: logs/backend.log${NC}"
    kill $BACKEND_PID 2>/dev/null || true
    exit 1
fi

echo -e "${GREEN}✅ 后端启动成功 (PID: $BACKEND_PID)${NC}"

# 启动前端
echo -e "${BLUE}⚛️  启动 Next.js 前端 (端口 3086)...${NC}"
cd frontend
npm run dev > ../logs/frontend.log 2>&1 &
FRONTEND_PID=$!
cd ..

echo ""
echo -e "${GREEN}✅ 所有服务已启动!${NC}"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo -e "${BLUE}📱 前端:${NC} http://localhost:3086"
echo -e "${BLUE}🔧 后端:${NC} http://localhost:8086"
echo -e "${BLUE}📊 API 文档:${NC} http://localhost:8086/docs"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo -e "${YELLOW}💡 提示:${NC}"
echo "  - 按 Ctrl+C 停止所有服务"
echo "  - 查看日志: tail -f logs/backend.log 或 logs/frontend.log"
echo ""

# 保存 PID 到文件
echo $BACKEND_PID > logs/backend.pid
echo $FRONTEND_PID > logs/frontend.pid

# 等待用户中断
trap "echo ''; echo '🛑 正在停止服务...'; kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; rm -f logs/*.pid; echo '✅ 所有服务已停止'; exit 0" INT TERM

# 保持脚本运行
wait

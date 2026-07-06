#!/bin/bash
# 千惠云端启动脚本 — 一键拉起 NapCat + bot.py
# 用法: bash /opt/maibot/start.sh

set -e

MAIBOT_ROOT="/opt/maibot"
cd "$MAIBOT_ROOT"

echo "=== 千惠云端启动 ==="

# 1. 启动 NapCat（如果没在跑）
if docker ps --format '{{.Names}}' | grep -q 'maim-bot-napcat'; then
    echo "[NapCat] 已在运行"
else
    echo "[NapCat] 启动中..."
    docker compose up -d
    echo "[NapCat] 已启动"
fi

# 2. 杀掉旧的 bot.py（如果残留）
if ps aux | grep -E "python.*bot\.py" | grep -v grep > /dev/null; then
    echo "[bot.py] 检测到旧进程，正在停止..."
    pkill -f "python.*bot\.py" 2>/dev/null || true
    sleep 2
fi

# 3. 清理僵尸 screen
screen -S maibot -X quit 2>/dev/null || true
sleep 0.5

# 4. 在 screen 中启动 bot.py
echo "[bot.py] 启动中..."
source .venv/bin/activate
screen -dmS maibot python3 bot.py
sleep 2

# 5. 检查状态
if ps aux | grep -E "python.*bot\.py" | grep -v grep > /dev/null; then
    echo "[bot.py] 已启动 (screen -r maibot 查看日志)"
else
    echo "[bot.py] 启动失败，请手动排查: cd $MAIBOT_ROOT && source .venv/bin/activate && python3 bot.py"
fi

echo "=== 完成 ==="
echo "NapCat WebUI: http://$(hostname -I | awk '{print $1}'):6099/webui/"
echo "Amadeus API:  http://$(hostname -I | awk '{print $1}'):8001/"
echo "查看日志:     screen -r maibot"

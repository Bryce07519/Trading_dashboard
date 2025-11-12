#!/bin/bash

# --- 确保脚本在正确的目录下运行 ---
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
cd "$SCRIPT_DIR"

# --- 设置 Git 用户信息 (如果需要) ---
git config user.name 'Performance Bot'
git config user.email 'bot@example.com'

# --- 运行 Python 脚本来更新数据和图表 ---
echo ">>> 正在运行 Python 脚本更新数据..."
python3 main.py

# --- 将生成的文件提交到 Git ---
echo ">>> 正在提交更新到 GitHub..."

# --- 核心修正：使用正确的文件路径 ---
# 我注意到你的日志里多了一个 pnl_hist.png，也把它加进去了
git add data/daily_pnl.csv data/stats.json data/equity_curve.png data/pnl_hist.png

# 检查是否有文件变动
if git diff --staged --quiet; then
  echo ">>> 文件没有变化，无需提交。"
else
  # 创建 commit
  COMMIT_MESSAGE="📊 Automated performance update on $(date -u)"
  git commit -m "$COMMIT_MESSAGE"
  
  # 推送到 GitHub
  git push origin main
  echo ">>> 成功推送到 GitHub！"
fi

echo ">>> 自动化更新流程完成。"
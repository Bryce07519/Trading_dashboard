#!/bin/bash

# 当任何命令失败时，立即退出脚本
set -e

# 切换到脚本所在的目录，确保所有路径都正确
cd "$( dirname "${BASH_SOURCE[0]}" )"

echo "======================================================"
echo "    🚀 Starting Data Sync to GitHub 🚀"
echo "======================================================"


# --- 运行 Python 脚本来更新数据和图表 ---
echo ">>> 正在运行 Python 脚本更新数据..."
python3 main.py

# --- 步骤 1: 与远程仓库同步 ---
# 使用 rebase 方式拉取，可以保持提交历史的整洁
# 这会把你本地的 data 文件夹改动，应用在远程最新版本之上
# echo ">>> Step 1: Pulling latest changes from GitHub..."
# git pull --rebase origin main
# echo "Sync with remote complete."
# echo

# --- 步骤 2: 将 data 文件夹的变更添加到暂存区 ---
# 这是脚本的核心，我们只关心 'data/' 目录
echo ">>> Step 2: Staging the 'data' folder for commit..."
git add data/
echo "'data' folder staged."
echo

# --- 步骤 3: 检查是否有变更并提交 ---
# 使用 'git diff --staged --quiet' 来检查是否有文件被暂存
# 如果没有，脚本会告知并干净地退出
if git diff --staged --quiet; then
  echo "✅ The 'data' folder has no new changes. All up to date!"
  echo "======================================================"
  exit 0
fi

echo ">>> Step 3: Changes detected in 'data' folder. Creating commit..."
# 创建一个标准化的提交信息
COMMIT_MESSAGE="chore(data): Update performance data on $(date -u)"
git commit -m "$COMMIT_MESSAGE"
echo "Commit created successfully."
echo

# --- 步骤 4: 推送到 GitHub ---
echo ">>> Step 4: Pushing data changes to GitHub..."
git push origin main
echo
echo "✅ Success! Your latest performance data is now live on GitHub."
echo "======================================================"
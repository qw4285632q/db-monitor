#!/bin/bash
# Database Monitor Startup Script
# 数据库监控系统启动脚本

cd "$(dirname "$0")"

echo "Starting Database Monitor..."
echo "数据库监控系统启动中..."

# Check Python version
python_version=$(python3 --version 2>&1 | awk '{print $2}')
echo "Python version: $python_version"

# Install dependencies if needed
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
else
    source venv/bin/activate
fi

# Start application
echo "Starting Flask application..."
python app_new.py


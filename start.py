#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Database Monitor Startup Script
数据库监控系统启动脚本
"""

import os
import sys
import subprocess

def main():
    print("=" * 60)
    print("Database Monitor - 数据库监控系统")
    print("=" * 60)
    
    # Check Python version
    if sys.version_info < (3, 8):
        print("错误: 需要 Python 3.8 或更高版本")
        print("当前版本:", sys.version)
        sys.exit(1)
    
    print(f"Python 版本: {sys.version.split()[0]}")
    
    # Check if in virtual environment
    if not hasattr(sys, 'real_prefix') and not (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix):
        print("\n建议使用虚拟环境:")
        print("  python -m venv venv")
        print("  source venv/bin/activate  # Linux/Mac")
        print("  venv\Scripts\activate     # Windows")
        print()
    
    # Check dependencies
    try:
        import flask
        import pymysql
        import pyodbc
        print("✓ 依赖包检查通过")
    except ImportError as e:
        print(f"✗ 缺少依赖包: {e}")
        print("\n请安装依赖:")
        print("  pip install -r requirements.txt")
        sys.exit(1)
    
    # Check config file
    if not os.path.exists('config.json'):
        print("\n✗ 配置文件不存在!")
        print("请复制配置模板并填写数据库连接信息:")
        print("  cp config.json.example config.json")
        print("  然后编辑 config.json 填入真实配置")
        sys.exit(1)
    
    print("✓ 配置文件检查通过")
    print("\n" + "=" * 60)
    print("启动 Flask 应用...")
    print("访问地址: http://localhost:5000")
    print("按 Ctrl+C 停止服务")
    print("=" * 60 + "\n")
    
    # Start Flask application
    try:
        import app_new
    except KeyboardInterrupt:
        print("\n\n服务已停止")
        sys.exit(0)
    except Exception as e:
        print(f"\n启动失败: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()

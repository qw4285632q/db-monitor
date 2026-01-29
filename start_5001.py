#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
启动脚本 - 端口5001
"""
import os
import sys

# 设置端口
os.environ['PORT'] = '5001'

# 执行主程序
if __name__ == '__main__':
    # 直接执行app_new.py的代码
    with open('app_new.py', 'r', encoding='utf-8') as f:
        exec(f.read())

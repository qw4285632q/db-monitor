#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
启动脚本 - 端口5001
"""
import os
os.environ['PORT'] = '5001'

# 导入并启动应用
if __name__ == '__main__':
    import app_new

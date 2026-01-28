#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
告警模块 - 支持企业微信、钉钉、邮件等多种告警方式
"""

import os
import json
import logging
import requests
from datetime import datetime
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class AlertChannel:
    """告警渠道基类"""

    def send(self, title: str, content: str, level: str = 'INFO') -> bool:
        """发送告警"""
        raise NotImplementedError


class WeComAlert(AlertChannel):
    """企业微信机器人告警"""

    def __init__(self, webhook_url: str):
        """
        初始化企业微信告警

        Args:
            webhook_url: 企业微信机器人Webhook地址
                        格式: https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxxxxxxx
        """
        self.webhook_url = webhook_url
        self.enabled = bool(webhook_url)

    def send(self, title: str, content: str, level: str = 'INFO') -> bool:
        """
        发送企业微信告警

        Args:
            title: 告警标题
            content: 告警内容
            level: 告警级别 INFO/WARNING/ERROR/CRITICAL
        """
        if not self.enabled:
            logger.warning("企业微信告警未配置，跳过发送")
            return False

        try:
            # 根据级别选择颜色
            colors = {
                'INFO': 'info',
                'WARNING': 'warning',
                'ERROR': 'warning',
                'CRITICAL': 'warning'
            }

            # Markdown格式消息
            markdown_content = f"""# {title}

> 级别: <font color="{colors.get(level, 'info')}">{level}</font>
> 时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

{content}
"""

            payload = {
                "msgtype": "markdown",
                "markdown": {
                    "content": markdown_content
                }
            }

            response = requests.post(
                self.webhook_url,
                json=payload,
                timeout=5
            )

            result = response.json()
            if result.get('errcode') == 0:
                logger.info(f"企业微信告警发送成功: {title}")
                return True
            else:
                logger.error(f"企业微信告警发送失败: {result}")
                return False

        except Exception as e:
            logger.error(f"企业微信告警发送异常: {e}")
            return False

    def send_deadlock_alert(self, deadlock_info: Dict) -> bool:
        """
        发送死锁告警

        Args:
            deadlock_info: 死锁信息
        """
        title = "🔴 数据库死锁告警"

        content = f"""
**数据库实例:** {deadlock_info.get('instance_name', 'Unknown')}
**实例地址:** {deadlock_info.get('db_ip')}:{deadlock_info.get('db_port')}
**数据库类型:** {deadlock_info.get('db_type', 'MySQL')}
**死锁时间:** {deadlock_info.get('deadlock_time', 'Unknown')}

**受害者会话:** {deadlock_info.get('victim_session_id', 'N/A')}
**受害者SQL:**
```sql
{deadlock_info.get('victim_sql', 'N/A')[:500]}
```

**阻塞者会话:** {deadlock_info.get('blocker_session_id', 'N/A')}
**阻塞者SQL:**
```sql
{deadlock_info.get('blocker_sql', 'N/A')[:500]}
```

**等待资源:** {deadlock_info.get('wait_resource', 'N/A')}
**锁模式:** {deadlock_info.get('lock_mode', 'N/A')}

**处理建议:**
1. 检查SQL是否使用了合适的索引
2. 优化事务大小，减少持锁时间
3. 调整应用程序访问顺序
"""

        return self.send(title, content, level='CRITICAL')

    def send_slow_sql_alert(self, slow_sql_info: Dict) -> bool:
        """
        发送慢SQL告警

        Args:
            slow_sql_info: 慢SQL信息
        """
        title = "⚠️ 慢SQL告警"

        elapsed_minutes = slow_sql_info.get('elapsed_minutes', 0)

        content = f"""
**数据库实例:** {slow_sql_info.get('instance_name', 'Unknown')}
**实例地址:** {slow_sql_info.get('db_ip')}:{slow_sql_info.get('db_port')}
**执行时长:** {elapsed_minutes:.2f} 分钟
**用户名:** {slow_sql_info.get('username', 'N/A')}
**客户端:** {slow_sql_info.get('machine', 'N/A')}
**程序:** {slow_sql_info.get('program', 'N/A')}

**SQL语句:**
```sql
{slow_sql_info.get('sql_text', 'N/A')[:500]}
```

**检测时间:** {slow_sql_info.get('detect_time', 'Unknown')}
**扫描行数:** {slow_sql_info.get('rows_examined', 'N/A')}
**返回行数:** {slow_sql_info.get('rows_sent', 'N/A')}
"""

        # 根据执行时长判断级别
        if elapsed_minutes > 10:
            level = 'CRITICAL'
        elif elapsed_minutes > 5:
            level = 'ERROR'
        else:
            level = 'WARNING'

        return self.send(title, content, level=level)


class DingTalkAlert(AlertChannel):
    """钉钉机器人告警"""

    def __init__(self, webhook_url: str, secret: Optional[str] = None):
        """
        初始化钉钉告警

        Args:
            webhook_url: 钉钉机器人Webhook地址
            secret: 加签密钥（可选）
        """
        self.webhook_url = webhook_url
        self.secret = secret
        self.enabled = bool(webhook_url)

    def _sign(self, timestamp: int) -> str:
        """生成签名"""
        if not self.secret:
            return ""

        import hmac
        import hashlib
        import base64
        import urllib.parse

        string_to_sign = f"{timestamp}\n{self.secret}"
        hmac_code = hmac.new(
            self.secret.encode('utf-8'),
            string_to_sign.encode('utf-8'),
            digestmod=hashlib.sha256
        ).digest()
        sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))
        return sign

    def send(self, title: str, content: str, level: str = 'INFO') -> bool:
        """发送钉钉告警"""
        if not self.enabled:
            return False

        try:
            timestamp = int(datetime.now().timestamp() * 1000)
            url = self.webhook_url

            if self.secret:
                sign = self._sign(timestamp)
                url = f"{url}&timestamp={timestamp}&sign={sign}"

            payload = {
                "msgtype": "markdown",
                "markdown": {
                    "title": title,
                    "text": f"### {title}\n\n{content}"
                }
            }

            response = requests.post(url, json=payload, timeout=5)
            result = response.json()

            if result.get('errcode') == 0:
                logger.info(f"钉钉告警发送成功: {title}")
                return True
            else:
                logger.error(f"钉钉告警发送失败: {result}")
                return False

        except Exception as e:
            logger.error(f"钉钉告警发送异常: {e}")
            return False


class EmailAlert(AlertChannel):
    """邮件告警"""

    def __init__(self, smtp_config: Dict):
        """
        初始化邮件告警

        Args:
            smtp_config: SMTP配置
                {
                    'host': 'smtp.example.com',
                    'port': 465,
                    'user': 'alert@example.com',
                    'password': 'password',
                    'from': 'alert@example.com',
                    'to': ['admin@example.com']
                }
        """
        self.smtp_config = smtp_config
        self.enabled = bool(smtp_config and smtp_config.get('host'))

    def send(self, title: str, content: str, level: str = 'INFO') -> bool:
        """发送邮件告警"""
        if not self.enabled:
            return False

        try:
            import smtplib
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart

            msg = MIMEMultipart()
            msg['From'] = self.smtp_config['from']
            msg['To'] = ', '.join(self.smtp_config['to'])
            msg['Subject'] = f"[{level}] {title}"

            html_content = f"""
            <html>
            <body>
                <h2>{title}</h2>
                <p><strong>级别:</strong> {level}</p>
                <p><strong>时间:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
                <hr>
                <pre>{content}</pre>
            </body>
            </html>
            """

            msg.attach(MIMEText(html_content, 'html'))

            if self.smtp_config['port'] == 465:
                server = smtplib.SMTP_SSL(self.smtp_config['host'], self.smtp_config['port'])
            else:
                server = smtplib.SMTP(self.smtp_config['host'], self.smtp_config['port'])
                server.starttls()

            server.login(self.smtp_config['user'], self.smtp_config['password'])
            server.send_message(msg)
            server.quit()

            logger.info(f"邮件告警发送成功: {title}")
            return True

        except Exception as e:
            logger.error(f"邮件告警发送异常: {e}")
            return False


class AlertManager:
    """告警管理器 - 支持多通道"""

    def __init__(self, config: Dict):
        """
        初始化告警管理器

        Args:
            config: 告警配置
                {
                    'wecom': {'webhook': 'https://...'},
                    'dingtalk': {'webhook': 'https://...', 'secret': '...'},
                    'email': {...}
                }
        """
        self.channels: List[AlertChannel] = []

        # 企业微信
        if config.get('wecom', {}).get('webhook'):
            self.channels.append(WeComAlert(config['wecom']['webhook']))

        # 钉钉
        if config.get('dingtalk', {}).get('webhook'):
            self.channels.append(DingTalkAlert(
                config['dingtalk']['webhook'],
                config['dingtalk'].get('secret')
            ))

        # 邮件
        if config.get('email', {}).get('host'):
            self.channels.append(EmailAlert(config['email']))

    def send_alert(self, title: str, content: str, level: str = 'INFO') -> bool:
        """发送告警到所有配置的通道"""
        if not self.channels:
            logger.warning("没有配置告警通道")
            return False

        success = False
        for channel in self.channels:
            try:
                if channel.send(title, content, level):
                    success = True
            except Exception as e:
                logger.error(f"告警通道发送失败: {e}")

        return success

    def send_deadlock_alert(self, deadlock_info: Dict) -> bool:
        """发送死锁告警"""
        success = False
        for channel in self.channels:
            try:
                if isinstance(channel, (WeComAlert, DingTalkAlert)):
                    if channel.send_deadlock_alert(deadlock_info):
                        success = True
                else:
                    # 其他通道使用通用格式
                    title = f"数据库死锁告警 - {deadlock_info.get('instance_name')}"
                    content = json.dumps(deadlock_info, indent=2, ensure_ascii=False)
                    if channel.send(title, content, 'CRITICAL'):
                        success = True
            except Exception as e:
                logger.error(f"死锁告警发送失败: {e}")

        return success

    def send_slow_sql_alert(self, slow_sql_info: Dict, threshold_minutes: float = 10) -> bool:
        """
        发送慢SQL告警（超过阈值才发送）

        Args:
            slow_sql_info: 慢SQL信息
            threshold_minutes: 告警阈值（分钟），默认10分钟
        """
        elapsed_minutes = slow_sql_info.get('elapsed_minutes', 0)

        # 只有超过阈值才发送告警
        if elapsed_minutes < threshold_minutes:
            return False

        success = False
        for channel in self.channels:
            try:
                if isinstance(channel, (WeComAlert, DingTalkAlert)):
                    if channel.send_slow_sql_alert(slow_sql_info):
                        success = True
                else:
                    title = f"慢SQL告警 - {slow_sql_info.get('instance_name')}"
                    content = json.dumps(slow_sql_info, indent=2, ensure_ascii=False)
                    level = 'CRITICAL' if elapsed_minutes > 30 else 'WARNING'
                    if channel.send(title, content, level):
                        success = True
            except Exception as e:
                logger.error(f"慢SQL告警发送失败: {e}")

        return success


def load_alert_config(config_file: str = 'alert_config.json') -> Dict:
    """加载告警配置"""
    try:
        if os.path.exists(config_file):
            with open(config_file, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"加载告警配置失败: {e}")

    # 返回默认配置（从环境变量读取）
    return {
        'wecom': {
            'webhook': os.getenv('WECOM_WEBHOOK', '')
        },
        'dingtalk': {
            'webhook': os.getenv('DINGTALK_WEBHOOK', ''),
            'secret': os.getenv('DINGTALK_SECRET', '')
        },
        'email': {
            'host': os.getenv('SMTP_HOST', ''),
            'port': int(os.getenv('SMTP_PORT', '465')),
            'user': os.getenv('SMTP_USER', ''),
            'password': os.getenv('SMTP_PASSWORD', ''),
            'from': os.getenv('SMTP_FROM', ''),
            'to': os.getenv('SMTP_TO', '').split(',') if os.getenv('SMTP_TO') else []
        }
    }


# 测试函数
if __name__ == '__main__':
    # 测试企业微信告警
    wecom = WeComAlert('YOUR_WEBHOOK_URL')

    # 测试死锁告警
    deadlock_info = {
        'instance_name': '生产环境主库',
        'db_ip': '192.168.1.100',
        'db_port': 3306,
        'db_type': 'MySQL',
        'deadlock_time': '2026-01-26 12:00:00',
        'victim_session_id': '12345',
        'victim_sql': 'UPDATE orders SET status = 1 WHERE id = 100',
        'blocker_session_id': '67890',
        'blocker_sql': 'UPDATE products SET stock = stock - 1 WHERE id = 50',
        'wait_resource': 'orders:PRIMARY',
        'lock_mode': 'X'
    }

    wecom.send_deadlock_alert(deadlock_info)

    # 测试慢SQL告警
    slow_sql_info = {
        'instance_name': '生产环境主库',
        'db_ip': '192.168.1.100',
        'db_port': 3306,
        'elapsed_minutes': 15.5,
        'username': 'app_user',
        'machine': '192.168.1.200',
        'program': 'java-app',
        'sql_text': 'SELECT * FROM big_table WHERE status = 1 AND created_at > NOW()',
        'detect_time': '2026-01-26 12:00:00',
        'rows_examined': 1000000,
        'rows_sent': 500
    }

    wecom.send_slow_sql_alert(slow_sql_info)

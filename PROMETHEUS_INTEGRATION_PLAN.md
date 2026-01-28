# Prometheus MySQL Exporter 整合方案

## 现状分析

### 已有的Prometheus基础设施

您已经部署了MySQL Exporter，监控以下实例：

```
端口    实例名称                    IP地址          状态    响应时间
19987  生产idcmysql备库1         192.168.44.71    UP     18.678ms
19993  预生产主库mysql           192.168.46.101   UP     23.870ms
19998  预生产备库库1mysql        192.168.46.102   UP     116.711ms
19994  生产idcmysql备库          192.168.44.141   UP     20.845ms
20010  阿里云生产mysql           10.111.1.152     UP     1.331s
20011  阿里云生产备库1mysql      10.111.3.22      UP     593.593ms
```

**关键优势**:
- ✅ 已经在收集丰富的指标数据
- ✅ 覆盖生产、预生产、IDC、阿里云等环境
- ✅ Exporter运行稳定（都是UP状态）
- ✅ 无需从零开始部署

---

## MySQL Exporter 提供的指标

### 1. 系统资源指标 ⭐

```promql
# CPU使用率
process_cpu_seconds_total

# 内存使用
process_resident_memory_bytes

# 文件描述符
process_open_fds
```

### 2. MySQL连接指标

```promql
# 当前连接数
mysql_global_status_threads_connected

# 最大连接数
mysql_global_variables_max_connections

# 连接使用率 = threads_connected / max_connections * 100

# 活跃连接
mysql_global_status_threads_running

# 历史最大连接
mysql_global_status_max_used_connections
```

### 3. QPS/TPS指标

```promql
# QPS (每秒查询数)
rate(mysql_global_status_questions[1m])

# TPS (每秒事务数)
rate(mysql_global_status_commands_total{command="commit"}[1m])
+ rate(mysql_global_status_commands_total{command="rollback"}[1m])

# 读写比例
rate(mysql_global_status_commands_total{command="select"}[1m])
rate(mysql_global_status_commands_total{command=~"insert|update|delete"}[1m])
```

### 4. InnoDB指标

```promql
# Buffer Pool命中率
(mysql_global_status_innodb_buffer_pool_read_requests
- mysql_global_status_innodb_buffer_pool_reads)
/ mysql_global_status_innodb_buffer_pool_read_requests * 100

# Buffer Pool使用率
mysql_global_status_innodb_buffer_pool_bytes_data
/ mysql_global_variables_innodb_buffer_pool_size * 100

# 脏页比例
mysql_global_status_innodb_buffer_pool_pages_dirty
/ mysql_global_status_innodb_buffer_pool_pages_total * 100

# 行锁等待
mysql_global_status_innodb_row_lock_waits
mysql_global_status_innodb_row_lock_time_avg
```

### 5. 磁盘IO指标

```promql
# 数据读取
rate(mysql_global_status_innodb_data_reads[1m])

# 数据写入
rate(mysql_global_status_innodb_data_writes[1m])

# 日志写入
rate(mysql_global_status_innodb_log_writes[1m])

# 页面读写
rate(mysql_global_status_innodb_pages_read[1m])
rate(mysql_global_status_innodb_pages_written[1m])
```

### 6. 复制延迟指标 ⭐

```promql
# 复制延迟（秒）
mysql_slave_status_seconds_behind_master

# 复制状态
mysql_slave_status_slave_io_running
mysql_slave_status_slave_sql_running

# 复制位置
mysql_slave_status_read_master_log_pos
mysql_slave_status_exec_master_log_pos
```

### 7. 慢查询指标

```promql
# 慢查询数量
rate(mysql_global_status_slow_queries[5m])

# 慢查询比例
rate(mysql_global_status_slow_queries[5m])
/ rate(mysql_global_status_questions[5m]) * 100
```

### 8. 表锁指标

```promql
# 表锁等待
mysql_global_status_table_locks_waited

# 锁等待比例
mysql_global_status_table_locks_waited
/ (mysql_global_status_table_locks_immediate + mysql_global_status_table_locks_waited) * 100
```

### 9. 临时表指标

```promql
# 临时表创建
rate(mysql_global_status_created_tmp_tables[1m])

# 磁盘临时表
rate(mysql_global_status_created_tmp_disk_tables[1m])

# 磁盘临时表比例（应该<25%）
rate(mysql_global_status_created_tmp_disk_tables[1m])
/ rate(mysql_global_status_created_tmp_tables[1m]) * 100
```

### 10. 线程缓存指标

```promql
# 线程创建速率
rate(mysql_global_status_threads_created[5m])

# 线程缓存命中率
(mysql_global_status_connections - mysql_global_status_threads_created)
/ mysql_global_status_connections * 100
```

---

## 整合方案

### 方案1: API代理方式 ⭐ **推荐**

通过Python后端查询Prometheus API，获取指标数据。

#### 优势
- ✅ 无需额外存储
- ✅ 实时数据
- ✅ 利用Prometheus的聚合计算
- ✅ 实现简单

#### 实现步骤

**1. 添加Prometheus配置**

```python
# config.json
{
    "prometheus": {
        "url": "http://192.168.98.4:9090",
        "timeout": 5
    }
}
```

**2. 创建Prometheus客户端**

```python
# scripts/prometheus_client.py
import requests
from datetime import datetime, timedelta

class PrometheusClient:
    def __init__(self, url):
        self.url = url.rstrip('/')
        self.api_url = f"{self.url}/api/v1"

    def query(self, promql):
        """执行即时查询"""
        response = requests.get(
            f"{self.api_url}/query",
            params={'query': promql},
            timeout=5
        )
        return response.json()

    def query_range(self, promql, start, end, step='15s'):
        """执行范围查询"""
        response = requests.get(
            f"{self.api_url}/query_range",
            params={
                'query': promql,
                'start': start,
                'end': end,
                'step': step
            },
            timeout=10
        )
        return response.json()

    def get_instance_metrics(self, instance_ip):
        """获取实例的关键指标"""
        metrics = {}

        # CPU使用率（需要node_exporter）
        cpu_query = f'rate(process_cpu_seconds_total{{instance=~".*{instance_ip}.*"}}[5m]) * 100'
        metrics['cpu_usage'] = self._extract_value(self.query(cpu_query))

        # 连接数
        conn_query = f'mysql_global_status_threads_connected{{instance=~".*{instance_ip}.*"}}'
        metrics['connections'] = self._extract_value(self.query(conn_query))

        # 最大连接数
        max_conn_query = f'mysql_global_variables_max_connections{{instance=~".*{instance_ip}.*"}}'
        metrics['max_connections'] = self._extract_value(self.query(max_conn_query))

        # QPS
        qps_query = f'rate(mysql_global_status_questions{{instance=~".*{instance_ip}.*"}}[1m])'
        metrics['qps'] = self._extract_value(self.query(qps_query))

        # TPS
        tps_query = f'''
        rate(mysql_global_status_commands_total{{command="commit",instance=~".*{instance_ip}.*"}}[1m])
        + rate(mysql_global_status_commands_total{{command="rollback",instance=~".*{instance_ip}.*"}}[1m])
        '''
        metrics['tps'] = self._extract_value(self.query(tps_query))

        # Buffer Pool命中率
        bp_query = f'''
        (mysql_global_status_innodb_buffer_pool_read_requests{{instance=~".*{instance_ip}.*"}}
        - mysql_global_status_innodb_buffer_pool_reads{{instance=~".*{instance_ip}.*"}})
        / mysql_global_status_innodb_buffer_pool_read_requests{{instance=~".*{instance_ip}.*"}} * 100
        '''
        metrics['buffer_pool_hit_rate'] = self._extract_value(self.query(bp_query))

        # 复制延迟
        repl_query = f'mysql_slave_status_seconds_behind_master{{instance=~".*{instance_ip}.*"}}'
        metrics['replication_lag'] = self._extract_value(self.query(repl_query))

        return metrics

    def _extract_value(self, response):
        """从Prometheus响应中提取值"""
        try:
            if response['status'] == 'success':
                result = response['data']['result']
                if result:
                    return float(result[0]['value'][1])
        except:
            pass
        return None
```

**3. 添加API端点**

```python
# app_new.py
from scripts.prometheus_client import PrometheusClient

# 初始化Prometheus客户端
prom_client = PrometheusClient(config['prometheus']['url'])

@app.route('/api/prometheus/metrics/<instance_ip>', methods=['GET'])
def get_prometheus_metrics(instance_ip):
    """获取Prometheus指标"""
    try:
        metrics = prom_client.get_instance_metrics(instance_ip)
        return jsonify({
            'success': True,
            'data': metrics
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/prometheus/query', methods=['POST'])
def prometheus_query():
    """执行自定义PromQL查询"""
    data = request.get_json()
    promql = data.get('query')

    try:
        result = prom_client.query(promql)
        return jsonify({
            'success': True,
            'data': result
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
```

**4. 前端集成**

```javascript
// 在性能指标页面添加Prometheus数据
async function loadPrometheusMetrics(instanceIp) {
    const result = await api(`/api/prometheus/metrics/${instanceIp}`);

    if (result.success) {
        const data = result.data;

        // 显示CPU使用率
        document.getElementById('cpuUsage').textContent =
            data.cpu_usage ? `${data.cpu_usage.toFixed(1)}%` : 'N/A';

        // 显示连接使用率
        const connUsage = (data.connections / data.max_connections * 100).toFixed(1);
        document.getElementById('connUsage').textContent = `${connUsage}%`;

        // 显示QPS/TPS
        document.getElementById('qps').textContent =
            data.qps ? Math.round(data.qps) : 0;
        document.getElementById('tps').textContent =
            data.tps ? Math.round(data.tps) : 0;

        // 显示Buffer Pool命中率
        document.getElementById('bpHitRate').textContent =
            data.buffer_pool_hit_rate ? `${data.buffer_pool_hit_rate.toFixed(2)}%` : 'N/A';

        // 显示复制延迟
        if (data.replication_lag !== null) {
            document.getElementById('replLag').textContent =
                `${data.replication_lag}秒`;
        }
    }
}
```

---

### 方案2: Grafana嵌入方式

直接在监控页面嵌入Grafana仪表板。

```html
<!-- 嵌入Grafana面板 -->
<div class="card">
    <div class="card-header">
        <span class="card-title">Prometheus监控指标</span>
    </div>
    <div class="card-body">
        <iframe
            src="http://192.168.98.4:3000/d/MQWgroiiz/mysql-exporter-quickstart-and-dashboard?orgId=1&refresh=5s&kiosk=tv"
            width="100%"
            height="600px"
            frameborder="0">
        </iframe>
    </div>
</div>
```

---

## 推荐的指标整合

### 1. 增强性能指标页面

在现有"性能指标"页面添加Prometheus数据：

```
当前（仅数据库层）         →  增强后（系统+数据库）
├─ QPS/TPS                  ├─ QPS/TPS（更精确，1分钟速率）
├─ 连接数                    ├─ 连接数 + 连接使用率趋势图
├─ 缓存命中率               ├─ Buffer Pool详细指标
└─ 阻塞查询                 ├─ 行锁等待统计
                            ├─ 表锁等待统计
                            ├─ CPU使用率 ⭐新增
                            ├─ 内存使用率 ⭐新增
                            ├─ 磁盘IO统计 ⭐新增
                            ├─ 慢查询比例 ⭐新增
                            └─ 临时表统计 ⭐新增
```

### 2. 新增系统资源页面

```
┌─────────────────────────────────────────┐
│ 系统资源监控                             │
├─────────────────────────────────────────┤
│ CPU使用率        内存使用率    磁盘IO     │
│  [75.5%]         [82.3%]      [65%]     │
│  趋势图          趋势图        趋势图     │
├─────────────────────────────────────────┤
│ 网络流量                                 │
│  入: 120MB/s     出: 95MB/s             │
│  趋势图                                  │
├─────────────────────────────────────────┤
│ InnoDB详细指标                           │
│  Buffer Pool命中率: 99.2%               │
│  脏页比例: 5.8%                          │
│  行锁等待: 12次/分钟                     │
└─────────────────────────────────────────┘
```

### 3. 增强复制监控

```
当前（基础状态）           →  增强后（详细指标）
├─ IO线程状态               ├─ IO线程状态
├─ SQL线程状态              ├─ SQL线程状态
├─ 延迟秒数                 ├─ 延迟秒数（实时）
└─ 错误信息                 ├─ 延迟趋势图（7天） ⭐新增
                            ├─ 复制位置差距 ⭐新增
                            ├─ 复制吞吐量 ⭐新增
                            └─ 延迟告警历史 ⭐新增
```

---

## 实现优先级

### 第一步：基础整合（1周）

1. **创建Prometheus客户端**
   - 实现query和query_range方法
   - 封装常用指标查询

2. **添加API端点**
   - `/api/prometheus/metrics/<ip>` - 获取实例指标
   - `/api/prometheus/query` - 执行自定义查询

3. **前端展示**
   - 在性能指标页面添加Prometheus数据
   - 显示CPU、内存、磁盘IO

### 第二步：深度整合（2周）

4. **新增系统资源页面**
   - 独立的系统资源监控tab
   - 趋势图表（基于Chart.js或ECharts）

5. **增强复制监控**
   - 复制延迟趋势图
   - 复制位置对比

6. **告警整合**
   - 基于Prometheus指标的告警
   - AlertManager集成

### 第三步：高级功能（3周）

7. **自定义仪表板**
   - 用户可配置监控面板
   - 拖拽式图表布局

8. **性能分析**
   - 资源使用趋势分析
   - 性能瓶颈识别

---

## 配置示例

### config.json

```json
{
    "database": {
        "host": "192.168.11.85",
        "port": 3306,
        "user": "root",
        "password": "Root#2025Jac.Com",
        "database": "db_monitor"
    },
    "prometheus": {
        "enabled": true,
        "url": "http://192.168.98.4:9090",
        "timeout": 5,
        "scrape_interval": "15s"
    },
    "grafana": {
        "enabled": false,
        "url": "http://192.168.98.4:3000",
        "api_key": ""
    },
    "exporter_mapping": {
        "192.168.44.71": "http://192.168.98.4:19987/metrics",
        "192.168.46.101": "http://192.168.98.4:19993/metrics",
        "192.168.46.102": "http://192.168.98.4:19998/metrics",
        "192.168.44.141": "http://192.168.98.4:19994/metrics",
        "10.111.1.152": "http://192.168.98.4:20010/metrics",
        "10.111.3.22": "http://192.168.98.4:20011/metrics"
    }
}
```

---

## 预期效果

### 整合前
❌ 只能看到SQL层面的问题
❌ 不知道是CPU、内存还是IO瓶颈
❌ 复制延迟只有一个数字
❌ 缺少历史趋势

### 整合后
✅ 完整的系统+数据库监控
✅ 清楚知道性能瓶颈在哪里
✅ 复制延迟有趋势图和告警
✅ 可以查看7天/30天历史数据
✅ 利用Prometheus强大的查询能力
✅ 无需重复采集数据

---

## 总结

有了Prometheus + MySQL Exporter，我们可以：

1. **填补系统资源监控的空白** - CPU、内存、磁盘IO
2. **增强现有功能** - 更精确的QPS/TPS、连接数
3. **添加趋势分析** - 利用Prometheus的时序数据
4. **实现告警功能** - 基于Prometheus AlertManager
5. **降低系统负担** - 无需重复采集已有数据

**这将使监控系统从75分提升到90分以上！**

下一步建议：
1. 先实现基础的Prometheus API查询
2. 在性能指标页面展示系统资源数据
3. 逐步添加趋势图表和高级功能

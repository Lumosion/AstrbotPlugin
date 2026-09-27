# AstrBot PEAK 每日地图插件

通过 `/peak` 获取 PEAK 今日地图。

通过 `/peak 变体` 查看全部地图区域、默认状态、变体名称和简单说明。

## 指令

### 仅查看地图

```text
/peak
```

默认只显示：

- 今日日期
- 每日地图类型
- 对应的变体名称
- 每个区域的简单介绍
- 一张包含各地图类型图标的汇总图片

## 特点

- 不接入 AI / LLM
- 直接从 PEAK 中文网站抓取数据
- 使用网页图标素材生成每日地图汇总图片
- 异步 HTTP 请求
- 网站异常时会返回错误信息

## 安装

将 `astrbot_plugin_peak` 文件夹放到：

```text
AstrBot/data/plugins/
```

安装依赖：

```bash
pip install -r requirements.txt
```

然后重启 AstrBot。

不要直接执行 `main.py`。它是 AstrBot 加载的插件入口，不是独立运行脚本；直接执行会因为当前 Python 环境没有 AstrBot 宿主模块而出现 `No module named 'astrbot'`。

## 数据源

https://peak.joaqu1m.com/zh-cn/

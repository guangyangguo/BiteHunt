# 探店地图 - 项目记忆

## 项目概述
美食探店搜集应用，以地图为核心展示知名博主探访过的店铺。

## 架构
```
前端 (frontend/)  ←→  Flask API (backend/)  ←→  SQLite (data/tandian.db)
                           ↓
                    B站API (视频采集)
                           ↓
                    LLM API (AI分析提取店铺)
```

## 技术栈
- **前端**：Leaflet.js + 高德瓦片 + 原生 JS
- **后端**：Python Flask（端口5000）
- **数据库**：SQLite（data/tandian.db）
- **AI分析**：OpenAI兼容API（默认DeepSeek）
- **视频采集**：B站公开API（含wbi签名）

## 文件结构
```
F:/tandian/
  frontend/               ← 前端（Flask 静态服务）
    index.html            ← 地图主页面
    admin.html            ← 管理后台
    css/style.css
    js/app.js             ← 地图逻辑（API动态加载）
    js/api.js             ← API通信层
    js/data.js            ← 静态数据（离线备用）
  backend/
    app.py                ← Flask 主应用
    database.py           ← SQLite CRUD
    services/
      bilibili.py         ← B站视频采集（wbi签名）
      analyzer.py         ← AI视频分析（LLM提取店铺）
    requirements.txt
  data/
    tandian.db            ← SQLite 数据库
```

## 核心流程
1. 管理后台搜索/添加B站UP主 → 自动拉取视频列表
2. 选择视频 → 调用LLM分析标题/描述/标签 → 提取店铺JSON
3. 通过Nominatim地理编码获取坐标
4. 店铺数据存入SQLite → 前端地图实时展示

## 启动命令
```bash
cd F:/tandian
python backend/app.py    # 启动后访问 http://localhost:5000
```

## 配置
- LLM API Key：在管理后台 → 系统配置 中设置
- 默认使用 DeepSeek API (deepseek-chat)

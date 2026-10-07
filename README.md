# 探店地图（Tandian）

探店地图将美食博主视频中的店铺信息整理为可搜索、可浏览的地图记录。后台可以采集 B 站博主与视频、调用 AI 提取店铺信息并完成地理编码；用户可通过 Web、小程序或 Android 客户端浏览店铺、获取推荐并收藏。

## 功能

- 地图浏览、关键词搜索、品类与博主筛选
- B 站博主、视频的采集与批量管理
- 视频字幕/音频转写、AI 店铺提取与地址地理编码
- AI 向导：基于偏好、预算、品类和距离推荐店铺
- 小程序定位、登录态与店铺收藏
- 后台的分析进度、分析步骤和店铺信息维护

## 项目结构

```text
.
├── backend/                 Flask API、数据库与 AI/采集服务
│   ├── services/            B 站采集、转写、分析、推荐、向导
│   ├── tests/               后端单元测试
│   └── .env.example         环境变量模板
├── frontend/                Web 地图前台与管理后台
├── wechat-miniprogram/      微信小程序用户端
├── android-client/          Android WebView 客户端
└── tests/                   小程序纯逻辑测试
```

## 本地启动

需要 Python 3.10+。以下命令以 PowerShell 为例：

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
python app.py
```

首次启动会创建本地 SQLite 数据库 `data/tandian.db`。服务启动后可访问：

- Web 地图：`http://localhost:5000/`
- 管理后台：`http://localhost:5000/admin.html`
- 健康检查：`http://localhost:5000/api/health`

默认数据库为 SQLite。若在 `backend/.env` 配置 `DATABASE_URL`，后端会改用 PostgreSQL；已有 SQLite 数据可使用 `backend/scripts/migrate_sqlite_to_postgres.py` 迁移。

## 配置

从 [backend/.env.example](backend/.env.example) 复制 `.env` 后，按需要填写以下值：

| 配置项 | 用途 | 是否必需 |
| --- | --- | --- |
| `LLM_API_URL`、`LLM_API_KEY`、`LLM_MODEL` | 视频分析模型 | 使用 AI 分析时必需 |
| `GUIDE_LLM_*` | AI 向导专用模型；留空时复用 LLM 配置 | 可选 |
| `AMAP_API_KEY` | 高德地理编码 | 可选 |
| `STT_*` | OpenAI 兼容或 Qwen ASR 转写服务 | 可选 |
| `BILIBILI_COOKIE` | B 站风控时的低频采集登录态 | 可选 |

`.env`、数据库文件和 Cookie 都不能提交到 Git。仓库仅保留占位模板。

## 微信小程序

1. 在微信开发者工具中导入 `wechat-miniprogram/`。
2. 在根目录和小程序目录的 `project.config.json` 中填入你自己的小程序 AppID。
3. 在 [wechat-miniprogram/utils/config.js](wechat-miniprogram/utils/config.js) 中把 `https://YOUR_API_DOMAIN/api` 改为自己的 HTTPS API 域名。
4. 在微信公众平台配置该域名为合法请求域名。

开发者工具可以连接本地服务；真机预览与发布必须使用手机可访问的 HTTPS 域名，不能提交局域网 IP。

## Android 客户端

Android 客户端通过 WebView 加载 Web 地图。模拟器默认地址为 `http://10.0.2.2:5000/`；真机或生产环境请在 `android-client/gradle.properties` 设置：

```properties
TANDIAN_WEB_URL=https://YOUR_WEB_DOMAIN/
```

项目未包含 Gradle Wrapper，可在 Android Studio 中构建，或在已安装 Gradle 的环境中执行：

```powershell
cd android-client
gradle :app:assembleDebug
```

## 测试

后端测试：

```powershell
cd backend
python -m unittest discover -s tests -p "test_*.py"
```

小程序纯逻辑测试：

```powershell
node tests/wechat-search-state.test.js
node tests/wechat-navigation.test.js
node tests/wechat-chat-state.test.js
```

## 上线前安全检查

- 使用 HTTPS，并关闭 Android 的明文流量配置。
- 使用微信 `code2Session` 校验登录，不接受客户端直接提供的 OpenID。
- 为管理、视频分析和分析日志接口增加管理员认证与授权。
- 不返回完整原始分析日志给普通用户；对日志中的用户或视频内容做脱敏。
- 将密钥存入部署环境的密钥管理服务，并在泄露后立即撤销和轮换。
- 发布前确认 Git 历史、CI 日志和构建产物均不含 `.env`、数据库、Cookie、Token 或真实域名/IP。

## 许可证

当前仓库未声明许可证。对外发布前请补充适合项目的许可证文件。

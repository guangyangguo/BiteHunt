# BiteHunt WeChat Mini Program

微信小程序用户展示端 MVP。Android 客户端仍保留在 `android-client/`，Web 后台仍使用现有 `frontend/admin.html`。

## 功能

- 原生 `map` 地图展示店铺坐标
- 顶部搜索
- 分类横向筛选
- 底部店铺抽屉
- 店铺详情底部弹层
- 用户定位
- 复用 Flask 后端 `/api/stores` 和 `/api/stats`

## 开发配置

默认 API 地址在 `utils/config.js`：

```js
apiBase: "http://127.0.0.1:5000/api"
```

这只适合微信开发者工具在本机调试。手机扫码预览时，`127.0.0.1` 会指向手机自己，不能访问电脑上的 Flask 服务。真机本地测试请先确认手机和电脑在同一 Wi-Fi，然后把地址改成电脑局域网 IP：

```js
apiBase: "http://192.168.x.x:5000/api"
```

电脑 IP 可以在 Windows 里执行 `ipconfig` 查看无线网卡的 IPv4 地址。上线前必须改成 HTTPS：

```js
apiBase: "https://your-domain.com/api"
```

同时需要在微信公众平台的小程序后台配置合法请求域名。

## 导入方式

1. 打开微信开发者工具。
2. 选择“导入项目”。
3. 项目目录选择 `F:\tandian\tandian-app\wechat-miniprogram`。
4. 没有 AppID 时可先使用测试号或游客模式。
5. 本地开发时可在开发者工具中关闭“校验合法域名”。

## 注意

- 小程序不能直接复用 Leaflet/HTML 展示页，因此这里使用原生 `map` 组件重写用户展示端。
- 后台管理不进入小程序，仍在 Web 端维护。
- 生产环境要求 HTTPS 后端域名。

# OpenRouter Free Proxy

帮你免费用 AI 模型的代理工具。不用管哪个模型能用，它会自动帮你找能用的。

## 有什么用？

**痛点：** OpenRouter 上面很多免费模型，但经常这个不能用、那个被限流，要手动换来换去很麻烦。

**解决：** 这个工具会自动帮你尝试多个模型，直到找到能用的为止。

## 三步上手

### 1. 安装

```bash
git clone https://github.com/lichengiggs/or-free-proxy.git
cd or-free-proxy
npm install
```

### 2. 启动

```bash
npm start
```

会看到提示：服务已启动 http://localhost:8765

### 3. 配置

打开浏览器访问 http://localhost:8765

**第一步：** 填 API Key
- 去 https://openrouter.ai/keys 注册账号（免费）
- 复制你的 Key，贴到网页里
- 点"保存并验证"

**第二步：** 选模型
- 页面会显示当前能用的模型（已验证过）
- 选你想用的，点"选择"
- 推荐用 `auto`，它会自动选最好的

**第三步（如果用 OpenClaw）：**
- 点"更新 OpenClaw 配置"
- 然后在 OpenClaw 里执行 `/model free_proxy/auto`

## 用好了

现在你的 AI 客户端（OpenClaw、Cursor 等）把 API 地址改成：

```
http://localhost:8765/v1
```

API Key 随便填，模型名也随便填，工具会自动处理。

## 常见问题

**Q: 为什么显示"无可用模型"？**
A: 免费模型有使用限制，等几分钟再刷新试试。

**Q: 为什么响应慢？**
A: 工具在逐个尝试模型，第一个失败就试下一个。正常 1-3 秒。

**Q: 支持哪些客户端？**
A: 任何支持 OpenAI API 格式的客户端都可以：OpenClaw、Cursor、Continue 等。

**Q: API Key 存在哪里？**
A: 存在本地 `.env` 文件，不会上传到任何地方。

## 命令速查

```bash
# 启动服务
npm start

# 停止服务
Ctrl + C

# 更新代码
git pull
npm install
```

## 开源协议

MIT - 随便用
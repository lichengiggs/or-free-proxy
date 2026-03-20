# or-free-proxy

[中文](README.md) | [English](README_EN.md)

一个本地 AI 代理工具：聚合 OpenRouter / Groq / OpenCode 的可用模型，自动回退，减少手动换模型。

适合个人使用，目标是「能稳定用上免费或低成本模型」。

## 功能

- 多 provider 支持：OpenRouter、Groq、OpenCode
- 自动回退：当前模型失败时自动尝试其他可用模型
- 手动添加模型：可添加临时免费或价格字段不准的模型
- 本地配置页面：保存 API Key、选模型、更新 OpenClaw 配置
- OpenAI 兼容接口：`http://localhost:8765/v1`

## 快速开始（3 步）

1) 安装依赖

```bash
git clone https://github.com/lichengiggs/or-free-proxy.git
cd or-free-proxy
npm install
```

2) 启动服务

```bash
npm start
```

3) 打开配置页面

- 浏览器访问：`http://localhost:8765`
- 至少保存 1 个 provider 的 API Key
- 选择模型（推荐 `openrouter/auto:free`）

## 页面怎么用（小白版）

### 第一步：保存 API Key（至少一个）

- OpenRouter: https://openrouter.ai/keys
- Groq: https://console.groq.com/keys
- OpenCode: https://opencode.ai/auth

说明：
- 三个 provider 都支持。
- 你只配置一个也能使用。

### 第二步：选模型

- 点“刷新模型列表”加载可用模型
- 选一个你要用的模型，点“选择”
- 不确定就选 `openrouter/auto:free`

### 第三步：必要时手动添加模型

如果某个模型你确认可用，但列表里没出现：

- 在“手动添加模型”中填写 `provider + modelId`
- 点击“验证并添加”
- 验证通过后，该模型会进入候选并参与自动回退

## 给客户端使用

任何支持 OpenAI API 的客户端都可以：OpenClaw、Cursor、Continue 等。

Base URL:

```txt
http://localhost:8765/v1
```

API Key:

- 客户端侧可填任意非空字符串（真正调用时由本代理转发到你保存的 provider key）

## OpenClaw（可选）

配置页面提供“更新 OpenClaw 配置”按钮，会自动写入 `~/.openclaw/openclaw.json` 并做备份。

## 常见问题

### 1) 保存 API Key 提示“网络错误”

- 请确认服务已启动：`npm start`
- 建议用 `http://localhost:8765` 打开页面（不要混用 127.0.0.1）

### 2) 提示“无可用模型”

- 免费模型会临时限流，先刷新模型列表再试
- 或手动添加一个你确认可用的模型

### 3) API Key 存在哪里？

- 存在项目根目录 `.env`（本地文件）
- 不会自动上传

## 开发命令

```bash
# 启动
npm start

# 测试
npm test

# 类型检查
npx tsc --noEmit
```

## 安全提醒

- 不要把 `.env` 提交到 GitHub
- 推送前先检查 `git status`

## License

MIT

# free_proxy

[中文](README.md) | [English](README_EN.md)

一个本地 AI 代理工具：聚合 OpenRouter / Groq / OpenCode / Gemini / GitHub Models / Mistral / Cerebras / SambaNova 的可用模型，自动回退，减少手动换模型。

适合个人使用，目标是「能稳定用上免费或低成本模型」。

## 功能

- 8 个 provider 支持：OpenRouter、Groq、OpenCode、Gemini、GitHub Models、Mistral、Cerebras、SambaNova
- 自动回退：当前模型失败时自动尝试其他可用模型
- 手动添加模型：可直接添加临时免费或价格字段不准的模型
- 本地配置页面：卡片式保存 API Key、直接选模型、更新 OpenClaw 配置
- OpenAI 兼容接口：`http://localhost:8765/v1`

## 快速开始（3 步）

1) 安装依赖

```bash
git clone https://github.com/lichengiggs/free_proxy.git
cd free_proxy
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
- Gemini: https://aistudio.google.com/app/apikey
- GitHub Models: https://github.com/settings/tokens
- Mistral: https://console.mistral.ai/api-keys
- Cerebras: https://cloud.cerebras.ai/
- SambaNova: https://cloud.sambanova.ai/

说明：
- 现在支持 8 个 provider。
- 你只配置一个也能使用。

### 第二步：选模型

- 点“刷新模型列表”加载可用模型
- 选一个你要用的模型，点“选择”
- 不确定就选 `openrouter/auto:free`

### 第三步：必要时手动添加模型

如果某个模型你确认可用，但列表里没出现：

- 在“手动添加模型”中填写 `provider + modelId`
- 点击“添加”
- 系统会直接保存，后续由自动回退兜底

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

补充说明：
- 如果你看到“自动回退到其他模型”，通常不是程序坏了，而是当前模型临时不可用（最常见是上游 429 限流或 key 配额用完）。
- 程序会自动切到其他可用模型，保证请求尽量不中断。

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

## 项目现状（小白可读）

目前这个项目已经稳定支持 8 个 provider：

- OpenRouter
- Groq
- OpenCode Zen
- Gemini
- GitHub Models
- Mistral
- Cerebras
- SambaNova

### 当前架构做了什么

- 前端只负责配置和直接选模型。
- 后端负责三件事：
  - 拉取各 provider 模型列表
  - 请求转发（OpenAI 兼容接口）
  - 自动回退（当前模型失败时换下一个）

### 现在的行为特点

- 不同 provider 用不同的必要请求头（不是一刀切），避免“某家能用、某家 400/403”的问题。
- Gemini 会自动做模型名规范化（`models/...`），减少调用报错。
- OpenRouter / OpenCode 的免费模型会优先参与候选，但如果上游限流会自动降级到其他 provider。
- 某模型恢复可用后，会自动从本地限流状态里清掉，不会长期被误跳过。

### 测试覆盖情况

- 已有测试 + 新增测试覆盖了：
  - provider header / 模型名规范化
  - fallback 关键路径与限流清理
  - 模型识别与归一化逻辑
  - 多 provider 的基础 API 行为
- 发布前建议再运行一次：
  - `npm test`
  - `npx tsc --noEmit`

如果你是第一次接触这类代理，可以这样理解：

- 这不是“固定只走一个模型”的直连程序。
- 它更像“会自动找可用模型”的调度器：优先你选的模型，失败就自动回退，保证可用性。

## 安全提醒

- 不要把 `.env` 提交到 GitHub
- 推送前先检查 `git status`

## License

MIT

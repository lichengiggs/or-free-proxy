# free_proxy

[中文](README.md) | [English](README_EN.md)

OpenClaw 免费 token 池：8 家 provider，免费、快、日常使用足够稳定。

把 OpenRouter / Groq / OpenCode / Gemini / GitHub Models / Mistral / Cerebras / SambaNova 的免费层拼成一个可用池。

可用的免费模型包括 `DeepSeek-V3.2`、`gemini-3.1-flash-lite`、`kimi-k2`、`GLM 4.5 Air`、`Step 3.5 Flash`、`GPT-4o Mini`，适合个人开发和日常编码。

### 免费额度亮点

| 方案 | 稳定性 | 额度 | 成本 |
|---|---:|---|---:|
| `free_proxy` | 中等，靠 fallback 保底 | 估算：约 3.3k 次/日（约 100k 次/月）；等价价值约 300USD/月；可支持并发开发（3–5 人同时使用）。基于 2026-03 对已配置 provider 与 Key 的战力盘点。 | 免费 |
| 美国付费 coding plan（OpenAI 示范） | 高 | 估算：约 200–10,000 次 1k-token 请求/月（对应 20–200USD/月 的消费范围） | 20-200USD/月 |
| 国内付费 coding plan（阿里云百炼示例） | 高 | Lite：18,000 次/月；Pro：90,000 次/月（官方说明） | Lite：7.9RMB（首月）；Pro：39.9RMB（首月） |

free_proxy 的卖点很直接：让 OpenClaw 先用上免费 token，再用自动回退把可用性兜住。

额度数字为保守估算，因 provider/地区/账号而异；free_proxy 聚合免费层 — 实际效果取决于上游限额。来源：阿里云百炼示例 https://developer.aliyun.com/article/1713813

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

- 选择模型
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
- 建议选择新出的大模型，通常免费量比较慷慨

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

## 为什么好用

- OpenClaw 直接填 `free_proxy/auto` 就能用免费 token。
- 前端只做卡片式配置和直接选模型，不绕验证。
- 后端负责拉取模型、转发请求、自动回退。
- 免费模型会优先参与候选，遇到限流会自动换下一个。

发布前建议再运行一次：`npm test` 和 `npx tsc --noEmit`

如果你是第一次接触这类代理，可以这样理解：

- 这不是“固定只走一个模型”的直连程序。
- 它更像“会自动找可用模型”的调度器：优先你选的模型，失败就自动回退，保证可用性。

## 安全提醒

- 不要把 `.env` 提交到 GitHub
- 推送前先检查 `git status`

## License

MIT

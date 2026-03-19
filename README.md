# OpenRouter Free Proxy

一个轻量级的 OpenRouter 免费模型代理服务，提供智能降级、Web 配置界面和 OpenClaw 一键集成功能。

## 功能特性

- 🤖 **智能模型降级** - 自动尝试多个免费模型，直到成功
- 🌐 **Web 配置界面** - 通过浏览器配置 API Key 和管理模型
- ✅ **模型可用性验证** - 只显示当前可用的模型
- 🔧 **OpenClaw 一键集成** - 自动配置 OpenClaw 客户端
- 💾 **配置备份恢复** - 自动备份 OpenClaw 配置，支持一键恢复
- 🚀 **零配置启动** - 默认自动选择最佳可用模型

## 快速开始

### 1. 安装

```bash
git clone <repository-url>
cd or-free-proxy
npm install
```

### 2. 启动服务

```bash
npm start
```

服务将在 http://localhost:8765 启动

### 3. 配置（首次使用）

1. 打开浏览器访问 http://localhost:8765
2. 输入你的 OpenRouter API Key（从 https://openrouter.ai/keys 获取）
3. 点击"保存并验证"
4. 在可用模型列表中选择你想使用的模型
5. 点击"更新 OpenClaw 配置"（如果使用 OpenClaw）

### 4. 使用

#### 直接 API 调用

```bash
curl -X POST http://localhost:8765/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your-api-key" \
  -d '{
    "model": "auto",
    "messages": [{"role": "user", "content": "Hello!"}],
    "max_tokens": 100
  }'
```

#### OpenClaw 配置

如果使用 OpenClaw，在配置成功后执行：

```bash
/model free_proxy/auto
```

或者使用具体模型：

```bash
/model free_proxy/meta-llama/llama-3.3-70b-instruct:free
```

## 配置说明

### 环境变量

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `OPENROUTER_API_KEY` | OpenRouter API Key | - |
| `PORT` | 服务端口 | 8765 |
| `OPENROUTER_BASE_URL` | OpenRouter API 地址 | https://openrouter.ai/api/v1 |

### 配置文件

项目会在首次运行时自动创建 `config.json` 文件：

```json
{
  "default_model": "auto"
}
```

## API 端点

### 聊天补全

```
POST /v1/chat/completions
```

兼容 OpenAI API 格式，支持流式输出。

### 获取模型列表

```
GET /admin/models
```

返回当前验证可用的免费模型列表。

### Web 界面

```
GET /
```

提供可视化的配置界面。

## 项目结构

```
or-free-proxy/
├── src/
│   ├── server.ts          # HTTP 服务器
│   ├── config.ts          # 配置管理
│   ├── models.ts          # 模型获取和过滤
│   ├── fallback.ts        # 降级逻辑
│   ├── rate-limit.ts      # 速率限制
│   ├── candidate-pool.ts  # 候选池管理
│   └── openclaw-config.ts # OpenClaw 配置
├── public/
│   └── index.html         # Web 界面
├── __tests__/             # 测试文件
├── package.json
└── README.md
```

## 开发

### 运行测试

```bash
npm test
```

### 代码检查

```bash
npx tsc --noEmit
```

## 注意事项

1. **免费模型限制** - OpenRouter 免费模型有速率限制，如果遇到 429 错误，请稍后再试
2. **模型可用性** - 免费模型的可用性会随时间变化，建议开启自动降级
3. **API Key 安全** - 请勿将 `.env` 文件提交到版本控制

## 技术栈

- **Runtime**: Node.js + TypeScript
- **Web Framework**: Hono
- **Testing**: Jest
- **Process Manager**: tsx

## 许可证

MIT

## 贡献

欢迎提交 Issue 和 Pull Request！
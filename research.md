# Free Proxy 深度研究报告

## 1. 项目概述

**项目名称**：Free Proxy (`free_proxy`)  
**核心目的**：本地多 Provider 免费 AI 模型代理服务  
**技术栈**：TypeScript + Hono + Jest 30 + tsx  
**运行环境**：Node.js (ESM 模式)  

---

## 2. 核心架构

### 2.1 入口与路由层

- **入口文件**：`src/server.ts`
- **HTTP 框架**：Hono (轻量级、高性能的边缘计算框架)
- **启动方式**：`tsx src/server.ts` 或 `tsx watch src/server.ts` (开发模式)
- **端口**：默认 8765，可通过 `PORT` 环境变量配置

**关键路由**：
- `POST /v1/chat/completions` — 核心代理转发接口
- `GET /admin/models` — 获取所有可用模型列表
- `PUT /admin/model` — 切换默认模型
- `POST /api/provider-keys` — 验证并保存 Provider Key
- `GET /api/provider-keys` — 获取所有 Provider Key 状态
- `POST /api/validate-key` — OpenRouter 专用 Key 验证
- `GET /api/health-check` — 健康检查
- `GET/POST/DELETE /api/custom-models` — 自定义模型 CRUD
- `GET/POST /api/detect-openclaw` — 检测和配置 OpenClaw

### 2.2 配置管理层 (`src/config.ts`)

**配置存储**：
- `config.json` — 应用配置（默认模型、自定义 Provider/Model）
- `.env` — 环境变量（API Keys）
- `rate-limit-state.json` — 限流状态持久化

**核心功能**：
1. **Provider Key 管理**：支持 8 个 Provider 的 Key 存储/读取/掩码
2. **Key 状态查询**：`getAllProviderKeysStatus()` 返回所有 Provider 的配置状态
3. **Key 掩码显示**：`maskApiKey()` 支持 `sk-or-` (6位前缀)、`gsk-` (4位)、其他 (3位) 三种格式
4. **HTTP 代理支持**：自动检测 `https_proxy`/`http_proxy` 环境变量，使用 undici 的 ProxyAgent
5. **文件写入锁**：防止并发写入 `.env` 文件冲突
6. **权限加固**：自动设置 `.env` 文件权限为 0o600 (仅所有者可读写)

### 2.3 Provider 注册中心 (`src/providers/registry.ts`)

**已注册 Provider**：

| Provider | Base URL | API Key Env | Format | 免费？ |
|----------|----------|-------------|--------|--------|
| openrouter | `https://openrouter.ai/api/v1` | `OPENROUTER_API_KEY` | openai | ✓ |
| groq | `https://api.groq.com/openai/v1` | `GROQ_API_KEY` | openai | ✓ |
| opencode | `https://opencode.ai/zen/v1` | `OPENCODE_API_KEY` | openai | ✓ |
| gemini | `https://generativelanguage.googleapis.com/v1beta` | `GEMINI_API_KEY` | gemini | ✓ |
| github | `https://models.github.ai/inference` | `GITHUB_MODELS_API_KEY` | openai | ✓ |
| mistral | `https://api.mistral.ai/v1` | `MISTRAL_API_KEY` | openai | ✓ |
| cerebras | `https://api.cerebras.ai/v1` | `CEREBRAS_API_KEY` | openai | ✓ |
| sambanova | `https://api.sambanova.ai/v1` | `SAMBANOVA_API_KEY` | openai | ✓ |

**Gemini 特殊处理**：Gemini 使用 Google 原生 `generateContent` API，而非 OpenAI 兼容格式。这导致了项目中多处存在 Gemini 特殊分支逻辑。

### 2.4 模型发现与过滤 (`src/models.ts`)

**核心流程**：
1. **模型获取**：`fetchAllModels()` 并行请求所有 Provider 的 `/models` 端点
2. **缓存机制**：每个 Provider 独立缓存，TTL 5 分钟
3. **模型过滤**：按 Provider 类型使用不同过滤策略：
   - **OpenRouter**：只显示免费模型（`pricing.prompt === 0 && pricing.completion === 0`）
   - **OpenCode**：只显示带 `-free` 后缀的模型
   - **Gemini**：硬编码白名单 `gemini-3.1-flash-lite-preview`、`gemma-3-27b-it`
   - **GitHub**：按任务类型、模型家族、名称关键词过滤聊天模型
   - **其他**：按 `isChatModel()` 判断是否为聊天模型

**模型 ID 标准化**：
- `normalizeGeminiModelId()` — 移除 `models/` 前缀
- `normalizeGithubModelId()` — 从 `/models/{id}/` 路径提取 ID
- `normalizeOpenCodeModelId()` — 移除 `models/` 前缀

**回退模型**：当 API 请求失败时，各 Provider 有硬编码的回退模型列表，确保至少有一个模型可用。

**模型评分系统**：
- 上下文长度评分 (0-40 分)
- Provider 信任度评分 (0-30 分)
- 参数量评分 (0-20 分)
- 综合排序，推荐最优模型

### 2.5 智能路由与回退机制 (`src/fallback.ts`)

**回退链构建** (`getFallbackChain()`)：
1. 首选模型（用户指定）
2. 自定义模型（按优先级排序）
3. 同 Provider 已验证模型
4. 全局评分最高的已验证模型
5. 其他已验证模型
6. 未验证模型
7. `openrouter/auto:free`（兜底选项）

**执行回退** (`executeWithFallback()`)：
- 遍历回退链，逐个尝试
- 跳过限流模型（`isModelRateLimited()`）
- 成功时标记模型可用，失败时标记不可用
- 支持 429/503 错误自动限流标记
- 所有失败时抛出详细错误信息，包含已尝试列表

**模型评分维度**：
- **稳定性**：OpenRouter/GitHub 最高，Groq/Mistral 次之
- **能力**：70B+ 模型 20 分，8B/mini 10 分
- **速度**：flash/lite 最快，70B/72B 较慢
- **上下文**：32K+ 最高，8K+ 标准
- **领域**：codestral/deepseek/qwen 编程能力强
- **白名单**：gpt-4o、llama-3.1-8b、codestral 等加分
- **黑名单**：gpt-3.5、tiny、deprecated 减分

### 2.6 限流管理 (`src/rate-limit.ts`)

**核心机制**：
- **持久化存储**：`rate-limit-state.json` 文件
- **内存缓存**：`memoryState` 避免重复文件读取
- **冷却时间**：30 分钟（`RATE_LIMIT_COOLDOWN_MINUTES`）
- **限流类型**：`rate_limit`、`unavailable`、`error`
- **自动清理**：`cleanExpiredRateLimits()` 清除过期记录

### 2.7 Provider 健康检查 (`src/provider-health.ts`)

**验证类型**：
- `validateProviderKey()` — 验证 Provider Key 是否有效
- `validateProviderKeyWithKey()` — 使用指定 Key 验证
- `verifyModelAvailability()` — 验证特定模型是否可用

**验证逻辑**：
- **Gemini**：使用 `POST /{model}:generateContent` 端点，发送 `ping` 消息
- **其他 Provider**：使用 `POST /chat/completions` 端点，发送 `ping` 消息
- **错误分类**：401/403 → `auth_failed`，其他 → `model_unavailable`，网络错误 → `network_error`

**HTTP 头构建**：
- **Gemini**：`x-goog-api-key` 头
- **OpenRouter**：`Authorization: Bearer` + `HTTP-Referer` + `X-Title`
- **其他**：`Authorization: Bearer`

### 2.8 OpenClaw 集成 (`src/openclaw-config.ts`)

**功能**：
- **检测**：检查 `~/.openclaw/openclaw.json` 是否存在且有效
- **配置**：自动创建/更新 OpenClaw 配置，添加 `free_proxy` provider
- **备份**：修改前自动创建备份（`openclaw.bak1`, `openclaw.bak2`, ...）
- **恢复**：支持从备份恢复配置

**配置格式**：
```json
{
  "models": {
    "providers": {
      "free_proxy": {
        "baseUrl": "http://localhost:8765/v1",
        "apiKey": "any_string",
        "api": "openai-completions",
        "models": [{ "id": "auto", "name": "auto" }]
      }
    }
  },
  "agents": {
    "defaults": {
      "models": {
        "free_proxy/auto": {}
      }
    }
  }
}
```

### 2.9 候选模型池 (`src/candidate-pool.ts`)

**功能**：
- **验证模型**：通过实际调用 API 验证模型是否可用
- **候选池管理**：维护已验证模型的列表
- **失败追踪**：记录模型失败次数，失败模型自动移除
- **手动添加**：支持手动添加模型到候选池

### 2.10 Provider 适配器层 (`src/providers/adapters/openai.ts`)

**设计模式**：适配器模式
- **OpenAIAdapter**：统一处理 OpenAI 兼容 API 和 Gemini API
- **Gemini 特殊逻辑**：
  - URL 构建：`/models/{model}:generateContent`
  - 请求体转换：`messages` → `contents` + `parts`
  - 认证头：`x-goog-api-key` 而非 `Authorization: Bearer`
  - 模型 ID 标准化：添加 `models/` 前缀

### 2.11 Provider 路由器 (`src/providers/router.ts`)

**功能**：
- **模型解析**：`parseModelId()` 解析 `provider/model` 格式
- **Provider 选择**：`getAvailableProviders()` 获取已配置 Key 的 Provider
- **回退执行**：`executeWithFallback()` 在 Provider 失败时自动切换
- **失败计数**：连续失败 3 次自动跳过该 Provider

---

## 3. 前端界面 (`public/index.html`)

### 3.1 功能模块

1. **Provider 配置区**：
   - 8 个 Provider 卡片网格，每个包含：
     - Provider 名称和免费/部分免费标签
     - API Key 输入框和保存按钮
     - 已配置状态显示和修改按钮
     - 获取 Key 的链接

2. **模型选择区**：
    - Provider 筛选标签页（全部 + 8 个 Provider）
    - 模型列表（显示名称、ID、当前选择）
    - 刷新模型列表按钮
    - 手动添加模型表单（支持选择 Provider、输入模型 ID、直接添加）

3. **OpenClaw 配置区**：
   - OpenClaw 状态检测
   - 一键配置按钮
   - 备份列表和恢复功能

### 3.2 交互流程

1. **初始化**：加载 Provider Key 状态 → 检测 OpenClaw → 加载自定义模型
2. **配置 Key**：输入 Key → 保存 → 更新状态 → 显示模型选择区
3. **选择模型**：筛选 Provider → 查看模型列表 → 直接选择模型 → 更新当前模型
4. **手动添加**：选择 Provider → 输入模型 ID → 直接保存 → 添加到候选池

---

## 4. 测试体系

### 4.1 测试配置

- **框架**：Jest 30 + ts-jest
- **运行方式**：`node --experimental-vm-modules node_modules/jest/bin/jest.js`
- **模块系统**：ESM（通过 `ts-jest` 的 `useESM` 选项）
- **测试环境**：Node.js

### 4.2 测试覆盖

**已覆盖模块**：
- Provider 注册与验证
- 多 Provider Key 管理
- 模型发现与过滤
- 回退机制
- 限流管理
- API 路由
- OpenClaw 配置

**测试文件统计**：
- 18 个测试文件
- 涵盖所有核心模块
- 支持模拟 `global.fetch` 进行 API 调用测试

### 4.3 测试模式

- **Red-Green 流程**：先写失败测试，再实现功能
- **模块隔离**：每个测试文件独立测试一个模块
- **环境清理**：`beforeEach`/`afterEach` 清理测试环境
- **模拟外部依赖**：使用 `global.fetch` 模拟 HTTP 请求

---

## 5. 关键设计决策

### 5.1 Gemini 特殊处理

**原因**：Google Gemini API 使用 `generateContent` 端点和 `x-goog-api-key` 认证，与 OpenAI 兼容 API 不同。

**影响范围**：
- `src/server.ts`：`buildUpstreamRequest()`、`transformGeminiResponse()`
- `src/config.ts`：`getProviderKey()` 支持文件读取 fallback
- `src/models.ts`：`normalizeGeminiModelId()`、`buildGeminiFallbackModels()`
- `src/provider-health.ts`：`buildProviderHeaders()`、`verifyModelAvailability()`
- `src/providers/adapters/openai.ts`：`normalizeProviderModelId()`、`buildChatURL()`、`buildRequestBody()`

### 5.2 Key 管理策略

**双存储机制**：
1. **环境变量**：启动时从 `.env` 加载到 `process.env`
2. **文件读取 fallback**：`getProviderKey()` 先查 `process.env`，再读 `.env` 文件

**原因**：开发服务器热重载时，`process.env` 不会自动更新 `.env` 文件的变更。

### 5.3 回退链策略

**优先级排序**：
1. 用户指定的首选模型
2. 自定义模型（按 priority 排序）
3. 同 Provider 已验证模型
4. 全局评分最高的模型
5. 其他已验证模型
6. 未验证模型
7. `openrouter/auto:free`（兜底）

**原因**：确保在任何情况下都能找到可用模型，同时优先使用用户偏好的模型。

### 5.4 模型评分系统

**评分维度**：
- **稳定性**：OpenRouter/GitHub 最稳定，Groq/Mistral 次之
- **能力**：70B+ 模型能力强，8B/mini 轻量快速
- **速度**：flash/lite 最快，70B/72B 较慢
- **上下文**：32K+ 上下文最长
- **领域**：编程、聊天、通用等不同领域
- **白名单/黑名单**：基于实际使用经验的加分/减分

**原因**：综合评估模型质量，自动推荐最优模型。

---

## 6. 已知问题与限制

### 6.1 OpenCode 限流

- **现象**：OpenCode 免费模型返回 429 `FreeUsageLimitError`
- **原因**：上游限流，非项目代码问题
- **解决方案**：等待限流重置或升级到付费版

### 6.2 OpenRouter 余额不足

- **现象**：返回 402 `Insufficient credits`
- **原因**：账号余额不足
- **解决方案**：充值或切换到其他 Provider

### 6.3 模型可用性验证延迟

- **现象**：后台仍会做可用性确认，但前端不再等待验证结果
- **原因**：模型发现和回退链依然依赖后端的可用性判断
- **解决方案**：前端直接切换，后端 fallback 兜底；验证作为后台能力保留

### 6.4 ESM 模块兼容性

- **现象**：Jest 测试需要特殊配置
- **原因**：项目使用 ESM，Jest 默认支持 CommonJS
- **解决方案**：使用 `--experimental-vm-modules` 和 `ts-jest` 的 `useESM` 选项

---

## 7. 项目结构总结

```
or_free_proxy/
├── src/
│   ├── server.ts           # HTTP 路由和请求处理
│   ├── config.ts           # 配置管理和 Provider Key 管理
│   ├── models.ts           # 模型发现、过滤和评分
│   ├── fallback.ts         # 智能路由和回退机制
│   ├── rate-limit.ts       # 限流状态管理
│   ├── provider-health.ts  # Provider 健康检查
│   ├── candidate-pool.ts   # 候选模型池管理
│   ├── openclaw-config.ts  # OpenClaw 配置集成
│   └── providers/
│       ├── registry.ts     # Provider 注册中心
│       ├── router.ts       # Provider 路由器
│       ├── types.ts        # 类型定义
│       └── adapters/
│           └── openai.ts   # OpenAI/Gemini 适配器
├── public/
│   └── index.html          # Web 管理界面
├── __tests__/              # 测试文件 (18 个)
├── .env                    # 环境变量 (API Keys)
├── config.json             # 应用配置
├── package.json            # 项目依赖
├── tsconfig.json           # TypeScript 配置
├── jest.config.js          # Jest 测试配置
└── plan.md                 # 开发计划
```

---

## 8. 核心数据流

### 8.1 聊天请求处理流程

```
客户端请求 → POST /v1/chat/completions
  ↓
解析模型 ID → provider/model 格式
  ↓
构建回退链 → 首选模型 → 自定义模型 → 评分排序模型 → 兜底模型
  ↓
遍历回逐 → 检查限流 → 构建请求 → 发送请求
  ↓
成功 → 返回响应 (Gemini 需转换格式)
失败 → 标记不可用 → 尝试下一个
  ↓
全部失败 → 抛出详细错误信息
```

### 8.2 模型发现流程

```
GET /admin/models
  ↓
检查是否有任何 Provider 配置了 Key
  ↓
并行请求所有 Provider 的 /models 端点
  ↓
按 Provider 类型过滤模型
  ↓
标准化模型 ID 和名称
  ↓
去重合并模型列表
  ↓
启动后台验证
  ↓
返回模型列表（包含验证状态）
```

---

## 9. 性能优化

### 9.1 缓存策略

- **模型缓存**：每个 Provider 独立缓存，TTL 5 分钟
- **配置缓存**：`cachedConfig` 避免重复文件读取
- **限流状态缓存**：`memoryState` 避免重复文件读取

### 9.2 并行处理

- **模型发现**：`Promise.all()` 并行请求所有 Provider
- **健康检查**：`Promise.all()` 并行验证所有 Provider
- **后台验证**：异步验证，不阻塞主流程

### 9.3 连接复用

- **HTTP 代理**：自动检测并配置 HTTP 代理，使用 undici 的 ProxyAgent
- **超时控制**：所有外部请求都有超时限制（默认 10 秒，模型验证 12 秒）

---

## 10. 安全考虑

### 10.1 API Key 保护

- **文件权限**：`.env` 文件自动设置为 0o600 (仅所有者可读写)
- **掩码显示**：前端显示时自动掩码，只显示前缀和后缀
- **环境变量**：通过 `.env` 文件管理，不提交到 Git

### 10.2 输入验证

- **API Key 格式**：验证 Key 格式（如 `sk-` 前缀）
- **模型 ID 验证**：验证模型 ID 格式
- **请求体验证**：验证请求体格式

### 10.3 错误处理

- **详细错误信息**：提供清晰的错误提示和解决建议
- **错误分类**：区分认证错误、网络错误、模型不可用等
- **敏感信息过滤**：不暴露 API Key 等敏感信息

---

## 11. 扩展性分析

### 11.1 添加新 Provider

**步骤**：
1. 在 `src/providers/registry.ts` 添加 Provider 配置
2. 在 `src/config.ts` 添加 Key 映射
3. 在 `src/models.ts` 添加模型过滤逻辑（如需要）
4. 在 `src/server.ts` 添加特殊处理（如需要）
5. 在 `src/provider-health.ts` 添加验证逻辑（如需要）
6. 在 `public/index.html` 添加 UI 组件

**示例**：Gemini 的添加涉及上述所有步骤，因为其 API 格式与 OpenAI 不同。

### 11.2 添加新功能

**扩展点**：
- **新路由**：在 `src/server.ts` 添加新路由
- **新配置**：在 `src/config.ts` 添加新配置项
- **新模型过滤**：在 `src/models.ts` 添加新过滤逻辑
- **新回退策略**：在 `src/fallback.ts` 添加新回退策略

---

## 12. 总结

Free Proxy 是一个设计良好的多 Provider AI 模型代理服务，具有以下特点：

1. **多 Provider 支持**：支持 8 个 Provider，统一管理
2. **智能路由**：基于评分和回退机制，自动选择最优模型
3. **Gemini 特殊处理**：完整的 Gemini API 适配，包括格式转换
4. **健康检查**：实时验证模型可用性
5. **限流管理**：自动处理 429/503 错误，智能回退
6. **OpenClaw 集成**：一键配置 OpenClaw，自动备份恢复
7. **Web 管理界面**：直观的 UI，支持模型选择和配置
8. **完善测试**：18 个测试文件，覆盖核心功能

**技术亮点**：
- 使用 Hono 框架，轻量高效
- ESM 模块系统，现代化
- TypeScript 类型安全
- 完善的错误处理和日志
- 良好的扩展性和可维护性

**潜在改进**：
- 模型评分可配置化
- 支持更多 Gemini 模型
- 添加请求日志和监控
- 支持模型优先级动态调整

# OpenRouter Free Proxy 功能增强实施计划

## 目标

让用户使用免费模型时**尽可能无感**，最大化利用免费 API 的能力，避免频繁手工切换模型。

## 核心原则

- **简单优先**：用最少的代码实现核心功能
- **渐进增强**：先跑起来，再优化
- **专注个人使用**：不需要过度考虑兼容性，保持代码简洁无负担

---

## Phase 1: 增强免费模型检测（1-2小时）

### 1.1 当前问题
仅检测 `:free` 后缀，可能漏掉一些 pricing=0 的免费模型

### 1.2 改进方案
双重检测：`:free` 后缀 + pricing=0

### 1.3 代码实现

```typescript
// src/models.ts
export interface OpenRouterModel {
  id: string;
  name: string;
  description: string;
  context_length: number;
  pricing: {
    prompt: string;
    completion: string;
  };
}

export function filterFreeModels(models: OpenRouterModel[]): OpenRouterModel[] {
  return models.filter(model => {
    // 方法1: :free 后缀
    if (model.id.endsWith(':free')) return true;
    
    // 方法2: pricing 为 0（更可靠）
    const promptCost = parseFloat(model.pricing?.prompt || '0');
    const completionCost = parseFloat(model.pricing?.completion || '0');
    if (promptCost === 0 && completionCost === 0) return true;
    
    return false;
  });
}
```

### 1.4 验证方式
```bash
curl http://localhost:8765/admin/models | jq '.models | length'
```

---

## Phase 2: 模型评分与智能推荐（2-3小时）

### 2.1 目标
自动识别性能最佳的免费模型，给用户提供「一键选择最佳」按钮

### 2.2 简化版评分算法

```typescript
// src/models.ts
export interface ModelScore {
  model: OpenRouterModel;
  score: number;
  reasons: string[];
}

const TRUSTED_PROVIDERS = [
  'google', 'meta-llama', 'mistralai', 'deepseek',
  'nvidia', 'qwen', 'microsoft', 'allenai'
];

export function rankModels(models: OpenRouterModel[]): ModelScore[] {
  return models.map(model => {
    let score = 0;
    const reasons: string[] = [];
    
    // 1. 上下文长度评分 (0-40分)
    const contextLength = model.context_length || 0;
    const contextScore = Math.min(contextLength / 32000, 1) * 40;
    score += contextScore;
    if (contextScore >= 40) reasons.push('超长上下文(32k+)');
    else if (contextScore >= 20) reasons.push('长上下文(16k+)');
    
    // 2. 提供商信任度 (0-30分)
    const provider = model.id.split('/')[0].toLowerCase();
    const providerIndex = TRUSTED_PROVIDERS.indexOf(provider);
    const providerScore = providerIndex >= 0 
      ? (1 - providerIndex / TRUSTED_PROVIDERS.length) * 30 
      : 10;
    score += providerScore;
    if (providerScore >= 25) reasons.push('知名提供商');
    
    // 3. 模型参数评分 (0-20分) - 从名称中提取参数数值
    const paramScore = extractParameterScore(model.name);
    score += paramScore.score;
    if (paramScore.reason) reasons.push(paramScore.reason);

    return { model, score: Math.round(score), reasons };
  }).sort((a, b) => b.score - a.score);
}

// 从模型名称中提取参数评分
function extractParameterScore(name: string): { score: number; reason?: string } {
  const match = name.match(/(\d+(?:\.\d+)?)\s*[bB]\b/);
  if (!match) return { score: 0 };

  const params = parseFloat(match[1]);

  if (params >= 70) {
    return { score: 20, reason: `大参数(${params}B)` };
  } else if (params >= 30) {
    return { score: 15, reason: `中参数(${params}B)` };
  } else if (params >= 13) {
    return { score: 10, reason: `标准参数(${params}B)` };
  } else if (params >= 7) {
    return { score: 5, reason: `轻量参数(${params}B)` };
  }

  return { score: 2, reason: `小参数(${params}B)` };
}

// 获取推荐模型
export function getRecommendedModel(models: OpenRouterModel[]): ModelScore | null {
  const ranked = rankModels(models);
  return ranked[0] || null;
}
```

### 2.3 API 接口更新

```typescript
// src/server.ts
app.get('/admin/models', async (c) => {
  try {
    const forceRefresh = c.req.query('refresh') === 'true';
    const models = await fetchModels(forceRefresh);
    const freeModels = filterFreeModels(models);
    const rankedModels = rankModels(freeModels);
    
    return c.json({
      models: rankedModels.map(({ model, score, reasons }) => ({
        id: model.id,
        name: model.name,
        context_length: model.context_length,
        score,
        reasons,
        is_recommended: score >= 80
      })),
      recommended: rankedModels[0]?.model.id
    });
  } catch (err: any) {
    console.error('Error fetching models:', err);
    return c.json({ error: err.message }, 500);
  }
});
```

### 2.4 Web UI 更新

```html
<div class="header">
  <h1>OpenRouter Free Proxy</h1>
  <div>
    <button class="btn btn-secondary" id="recommendBtn">🎖️ 使用推荐模型</button>
    <button class="btn" id="refreshBtn">刷新模型列表</button>
  </div>
</div>

<div id="recommendedBanner" style="display: none;" class="banner">
  🏆 智能推荐: <span id="recommendedName"></span> 
  评分: <span id="recommendedScore"></span>
  <button class="btn btn-small" onclick="useRecommended()">一键使用</button>
</div>

<script>
async function loadModels(forceRefresh = false) {
  const res = await fetch(url);
  const data = await res.json();
  
  if (data.recommended) {
    const recommended = data.models.find(m => m.id === data.recommended);
    if (recommended) {
      document.getElementById('recommendedName').textContent = recommended.name;
      document.getElementById('recommendedScore').textContent = recommended.score;
      document.getElementById('recommendedBanner').style.display = 'block';
    }
  }
}
</script>
```

---

## Phase 3: Fallback 机制 + 速率限制处理（核心，4-6小时）

### 3.1 设计目标
- 用户选择的模型不可用时，自动切换到备选模型
- 记录速率限制状态，避免重复尝试已限流的模型
- 通过响应头告知用户实际使用的模型

### 3.2 数据结构设计

```typescript
// src/rate-limit.ts
import { readFile, writeFile } from 'node:fs/promises';
import { existsSync } from 'node:fs';

interface RateLimitState {
  [modelId: string]: {
    limited_at: string;
    retry_after?: number;
    reason: 'rate_limit' | 'unavailable' | 'error';
  };
}

const RATE_LIMIT_FILE = 'rate-limit-state.json';
const RATE_LIMIT_COOLDOWN_MINUTES = 30;

let memoryState: RateLimitState | null = null;

export async function loadRateLimitState(): Promise<RateLimitState> {
  if (memoryState) return memoryState;
  
  if (!existsSync(RATE_LIMIT_FILE)) {
    memoryState = {};
    return memoryState;
  }
  
  try {
    const content = await readFile(RATE_LIMIT_FILE, 'utf-8');
    memoryState = JSON.parse(content);
    return memoryState;
  } catch {
    memoryState = {};
    return memoryState;
  }
}

export async function saveRateLimitState(state: RateLimitState) {
  memoryState = state;
  await writeFile(RATE_LIMIT_FILE, JSON.stringify(state, null, 2));
}

export function isModelRateLimited(modelId: string): boolean {
  const state = memoryState || {};
  const record = state[modelId];
  if (!record) return false;
  
  const limitedAt = new Date(record.limited_at);
  const cooldownEnd = new Date(limitedAt.getTime() + RATE_LIMIT_COOLDOWN_MINUTES * 60 * 1000);
  return Date.now() < cooldownEnd.getTime();
}

export async function markModelRateLimited(
  modelId: string, 
  reason: 'rate_limit' | 'unavailable' | 'error' = 'rate_limit',
  retryAfter?: number
) {
  const state = await loadRateLimitState();
  state[modelId] = {
    limited_at: new Date().toISOString(),
    retry_after: retryAfter,
    reason
  };
  await saveRateLimitState(state);
  console.log(`[RateLimit] Model ${modelId} marked as ${reason}`);
}
```

### 3.3 Fallback 核心实现

```typescript
// src/config.ts
export interface Config {
  preferred_model?: string;  // 用户偏好（可选），默认用评分最高的
}

export const DEFAULT_CONFIG: Config = {
  preferred_model: undefined  // 未设置时使用自动推荐
};
```

```typescript
// src/fallback.ts
import { getConfig } from './config';
import { isModelRateLimited, markModelRateLimited } from './rate-limit';
import { fetchModels, filterFreeModels, rankModels } from './models';

export interface FallbackResult {
  model: string;
  is_fallback: boolean;
  attempted_models: string[];
  fallback_reason?: string;
}

export async function getFallbackChain(preferredModel?: string): Promise<string[]> {
  const chain: string[] = [];
  
  // 1. 添加用户偏好模型（如果有）
  if (preferredModel) {
    chain.push(preferredModel);
  }
  
  // 2. 添加评分最高的前3个免费模型
  try {
    const models = await fetchModels();
    const freeModels = filterFreeModels(models);
    const ranked = rankModels(freeModels);
    
    for (const { model } of ranked.slice(0, 3)) {
      if (!chain.includes(model.id)) {
        chain.push(model.id);
      }
    }
  } catch (err) {
    console.error('[Fallback] Failed to get fallback models:', err);
  }
  
  // 3. 最后兜底：openrouter/free
  if (!chain.includes('openrouter/free')) {
    chain.push('openrouter/free');
  }
  
  return chain;
}

export async function executeWithFallback<T>(
  preferredModel: string | undefined,
  execute: (model: string) => Promise<{ success: boolean; response?: T; error?: any }>
): Promise<{ result: T; fallbackInfo: FallbackResult }> {
  const chain = await getFallbackChain(preferredModel);
  const attemptedModels: string[] = [];
  
  for (const model of chain) {
    if (isModelRateLimited(model)) {
      console.log(`[Fallback] Skipping ${model} (rate limited)`);
      attemptedModels.push(`${model}(rate_limited)`);
      continue;
    }
    
    console.log(`[Fallback] Trying model: ${model}`);
    const { success, response, error } = await execute(model);
    
    if (success && response) {
      return {
        result: response,
        fallbackInfo: {
          model,
          is_fallback: model !== preferredModel,
          attempted_models: attemptedModels,
          fallback_reason: model !== preferredModel 
            ? `${preferredModel || 'auto-selected'} unavailable, fallback to ${model}` 
            : undefined
        }
      };
    }
    
    attemptedModels.push(model);
    
    if (error?.status === 429) {
      await markModelRateLimited(model, 'rate_limit', error.retry_after);
    } else if (error?.status === 503) {
      await markModelRateLimited(model, 'unavailable');
    }
  }
  
  throw new Error(`All models failed. Attempted: ${attemptedModels.join(', ')}`);
}
```

### 3.4 集成到 Server

```typescript
// src/server.ts
import { executeWithFallback } from './fallback';

app.post('/v1/chat/completions', async (c) => {
  try {
    const body = await c.req.json();
    const headers = Object.fromEntries(c.req.raw.headers.entries());
    const config = await getConfig();
    
    const result = await executeWithFallback(
      config.preferred_model,
      async (modelToTry) => {
        body.model = modelToTry;
        
        const proxyHeaders: Record<string, string> = {
          'Authorization': `Bearer ${ENV.OPENROUTER_API_KEY}`,
          'HTTP-Referer': 'http://localhost:8765',
          'X-Title': 'OpenRouter Free Proxy',
          'Content-Type': 'application/json'
        };
        
        Object.entries(headers).forEach(([key, value]) => {
          if (!['host', 'content-length', 'authorization'].includes(key.toLowerCase())) {
            proxyHeaders[key] = value;
          }
        });
        
        try {
          const response = await fetchWithTimeout(
            `${ENV.OPENROUTER_BASE_URL}/chat/completions`,
            {
              method: 'POST',
              headers: proxyHeaders,
              body: JSON.stringify(body)
            },
            60000
          );
          
          if (response.ok) {
            return { success: true, response };
          }
          
          const errorBody = await response.text();
          return {
            success: false,
            error: {
              status: response.status,
              message: errorBody,
              retry_after: response.headers.get('retry-after')
            }
          };
        } catch (err: any) {
          return { success: false, error: { message: err.message } };
        }
      }
    );
    
    const response = result.result;
    const fallbackInfo = result.fallbackInfo;
    
    c.header('X-Actual-Model', fallbackInfo.model);
    if (fallbackInfo.is_fallback) {
      c.header('X-Fallback-Used', 'true');
      c.header('X-Fallback-Reason', fallbackInfo.fallback_reason || 'Primary model unavailable');
    }
    
    if (body.stream) {
      const responseHeaders = Object.fromEntries(response.headers.entries());
      c.status(response.status as any);
      Object.entries(responseHeaders).forEach(([key, value]) => {
        if (key.toLowerCase() !== 'content-encoding') {
          c.header(key, value);
        }
      });
      
      return stream(c, async (stream) => {
        if (!response.body) return;
        const reader = response.body.getReader();
        let done = false;
        while (!done) {
          const chunk = await reader.read();
          done = chunk.done;
          if (!done && chunk.value) await stream.write(chunk.value);
        }
      });
    }
    
    const data = await response.json();
    return c.json(data, { status: response.status as any });
    
  } catch (err: any) {
    console.error(`[${new Date().toISOString()}] Request error:`, err.message);
    return c.json({
      error: {
        message: err.message,
        type: 'internal_error',
        code: 500
      }
    }, 500);
  }
});
```

---

## Phase 4: 简化与清理（1小时）

### 4.1 最终架构

```
用户请求
   ↓
有偏好模型？→ 是 → 尝试偏好模型
   ↓ 否
自动选择评分最高模型
   ↓
模型可用？→ 是 → 使用
   ↓ 否
尝试 Fallback 链（评分排序）
   ↓
遇到 429？→ 标记冷却 → 尝试下一个
   ↓
返回结果 + X-Actual-Model
```

### 4.2 最小化配置

```typescript
// src/config.ts
interface Config {
  preferred_model?: string;  // 可选，用户偏好
}

// .env
OPENROUTER_API_KEY=xxx
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
PORT=8765
```

### 4.3 API 接口

```
POST   /v1/chat/completions    # 核心：带自动 fallback
GET    /admin/models           # 获取免费模型列表（带评分）
PUT    /admin/model            # 设置偏好模型（可选）
GET    /                       # Web UI
```

---

## 实施顺序

```
Day 1: Phase 1 (pricing=0 检测)
Day 2: Phase 2 (模型评分 + 推荐)
Day 3-4: Phase 3 (Fallback 核心)
Day 5: Phase 4 (简化清理)
```

### 验收标准

**Phase 1**:
- [ ] 模型列表比原来多
- [ ] pricing=0 模型被正确识别

**Phase 2**:
- [ ] Web UI 显示「🎖️ 使用推荐模型」按钮
- [ ] 点击后自动切换到评分最高的模型
- [ ] 模型列表显示评分

**Phase 3**:
- [ ] 连续发送 20 个请求，不会遇到 429 错误
- [ ] 响应头 `X-Actual-Model` 显示实际使用的模型
- [ ] 故意选择限速模型，自动 fallback 成功

---

## 资源消耗

| 功能 | 内存消耗 | 额外请求 |
|------|---------|---------|
| pricing=0 检测 | 0 | 0 |
| 模型评分 | ~100KB | 0 |
| Fallback 机制 | ~50KB | 失败时 N 次 |

**总内存**：< 200KB

---

## 最终效果

- **默认行为**：自动使用评分最高的免费模型
- **用户可选**：在 Web UI 选择偏好模型
- **自动处理**：fallback、速率限制、冷却
- **透明告知**：响应头显示实际使用的模型

**体验目标**：「无感使用免费 API」，无需手工切换

---

## 完整任务清单

### Phase 1: 增强免费模型检测（Day 1）✅

- [x] 1.1 更新 `src/models.ts`
  - [x] 1.1.1 修改 `OpenRouterModel` 接口，添加 pricing 字段
  - [x] 1.1.2 修改 `filterFreeModels` 函数，实现双重检测逻辑
  - [x] 1.1.3 添加单元测试验证 pricing=0 检测

- [x] 1.2 验证
  - [x] 1.2.1 启动服务
  - [x] 1.2.2 调用 `/admin/models` 接口
  - [x] 1.2.3 确认模型数量比原来多

### Phase 2: 模型评分与智能推荐（Day 2）✅

- [x] 2.1 更新 `src/models.ts`
  - [x] 2.1.1 添加 `ModelScore` 接口
  - [x] 2.1.2 添加 `TRUSTED_PROVIDERS` 常量
  - [x] 2.1.3 实现 `rankModels` 评分函数
  - [x] 2.1.4 实现 `extractParameterScore` 参数提取函数
  - [x] 2.1.5 实现 `getRecommendedModel` 函数
  - [x] 2.1.6 添加单元测试

- [x] 2.2 更新 `src/server.ts`
  - [x] 2.2.1 修改 `/admin/models` 接口，调用 `rankModels`
  - [x] 2.2.2 返回评分和推荐理由

- [x] 2.3 更新 `public/index.html`
  - [x] 2.3.1 添加「🎖️ 使用推荐模型」按钮
  - [x] 2.3.2 添加推荐横幅展示区域
  - [x] 2.3.3 修改 `loadModels` 函数，显示评分
  - [x] 2.3.4 实现 `useRecommended` 函数

- [x] 2.4 验证
  - [x] 2.4.1 Web UI 显示评分
  - [x] 2.4.2 点击「使用推荐模型」切换到最高评分的模型

### Phase 3: Fallback 机制 + 速率限制处理（Day 3-4）✅

- [x] 3.1 创建 `src/rate-limit.ts`
  - [x] 3.1.1 定义 `RateLimitState` 接口
  - [x] 3.1.2 实现 `loadRateLimitState` 函数
  - [x] 3.1.3 实现 `saveRateLimitState` 函数
  - [x] 3.1.4 实现 `isModelRateLimited` 函数
  - [x] 3.1.5 实现 `markModelRateLimited` 函数
  - [x] 3.1.6 添加单元测试

- [x] 3.2 更新 `src/config.ts`
  - [x] 3.2.1 修改 `Config` 接口，使用 `preferred_model?: string`
  - [x] 3.2.2 更新 `DEFAULT_CONFIG`

- [x] 3.3 创建 `src/fallback.ts`
  - [x] 3.3.1 定义 `FallbackResult` 接口
  - [x] 3.3.2 实现 `getFallbackChain` 函数
  - [x] 3.3.3 实现 `executeWithFallback` 函数
  - [x] 3.3.4 添加单元测试

- [x] 3.4 更新 `src/server.ts`
  - [x] 3.4.1 导入 `executeWithFallback`
  - [x] 3.4.2 重写 `/v1/chat/completions` 处理逻辑
  - [x] 3.4.3 添加 `X-Actual-Model` 响应头
  - [x] 3.4.4 添加 `X-Fallback-Used` 响应头
  - [x] 3.4.5 添加 `X-Fallback-Reason` 响应头

- [x] 3.5 验证
  - [x] 3.5.1 连续发送 20 个请求，无 429 错误
  - [x] 3.5.2 检查响应头显示实际模型
  - [x] 3.5.3 选择一个被限速的模型，验证自动 fallback
  - [x] 3.5.4 检查 `rate-limit-state.json` 文件生成

### Phase 4: 简化与清理（Day 5）✅

- [x] 4.1 代码审查与清理
  - [x] 4.1.1 删除未使用的导入
  - [x] 4.1.2 删除未使用的变量和函数
  - [x] 4.1.3 检查并修复 TypeScript 类型错误

- [x] 4.2 测试
  - [x] 4.2.1 运行 `npm test`，确保所有测试通过
  - [x] 4.2.2 测试流式响应
  - [x] 4.2.3 测试非流式响应
  - [x] 4.2.4 测试 Web UI 所有功能

- [x] 4.3 文档更新
  - [x] 4.3.1 更新 README.md，说明新功能
  - [x] 4.3.2 添加使用示例
  - [x] 4.3.3 添加截图说明

- [x] 4.4 最终验证
  - [x] 4.4.1 完整流程测试
  - [x] 4.4.2 性能测试（内存占用）
  - [x] 4.4.3 长时间运行测试（30分钟）

---

## 项目完成后结构

```
or_free_proxy/
├── src/
│   ├── server.ts          # 主服务（修改）
│   ├── models.ts          # 模型检测与评分（修改）
│   ├── config.ts          # 配置管理（修改）
│   ├── rate-limit.ts      # 速率限制管理（新增）
│   └── fallback.ts        # Fallback 逻辑（新增）
├── public/
│   └── index.html         # Web UI（修改）
├── __tests__/
│   ├── models.test.ts     # 模型测试
│   ├── rate-limit.test.ts # 速率限制测试
│   └── fallback.test.ts   # Fallback 测试
├── config.json            # 用户偏好配置
├── rate-limit-state.json  # 速率限制状态
├── .env                   # API Key
├── package.json
├── tsconfig.json
└── README.md
```

---

## 验收标准总览

| 功能 | 验收标准 | 状态 |
|------|----------|------|
| 免费模型检测 | 模型列表包含 pricing=0 的模型 | ✅ |
| 模型评分 | Web UI 显示评分和推荐理由 | ✅ |
| 智能推荐 | 一键使用评分最高的模型 | ✅ |
| Fallback 机制 | 失败时自动切换，响应头告知 | ✅ |
| 速率限制 | 30分钟冷却，避免重复请求 | ✅ |
| 流式响应 | 支持流式输出，无延迟 | ✅ |
| 测试覆盖 | 所有核心功能都有单元测试 | ✅ |

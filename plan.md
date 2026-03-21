# 多 Provider 接入计划

目标：新增并跑通 `Gemini` / `GitHub Models` / `Mistral` / `Cerebras` / `SambaNova`。

核心原则：
- 先各自独立接入，先跑通。
- 不提前抽统一适配层。
- 先保留 provider 特殊逻辑，等都稳定后再考虑合并。
- 某些 provider 如果天然不同，就允许一直独立。

---

## 1. 现状

当前真正注册的 provider 只有 3 个：
- `openrouter`
- `groq`
- `opencode`

这次要补回/新增：
- `gemini`
- `github`
- `mistral`
- `cerebras`
- `sambanova`
---

## 2. 总体策略

先把每个 provider 当成独立接入点处理：

1. 独立 key 保存
2. 独立 key 校验
3. 独立模型列表拉取
4. 独立最小调用验证
5. 独立 fallback/路由适配

等全部跑通后，再看哪些逻辑能合并。

---

## 3. 计划拆分

### 3.1 先扩展 provider 注册表

先把 provider 元信息补齐，不做统一抽象。

```ts
export const PROVIDERS: Provider[] = [
  { name: 'openrouter', baseURL: 'https://openrouter.ai/api/v1', apiKeyEnv: 'OPENROUTER_API_KEY', format: 'openai', isFree: true },
  { name: 'groq', baseURL: 'https://api.groq.com/openai/v1', apiKeyEnv: 'GROQ_API_KEY', format: 'openai', isFree: true },
  { name: 'opencode', baseURL: 'https://opencode.ai/zen/v1', apiKeyEnv: 'OPENCODE_API_KEY', format: 'openai', isFree: true },
  { name: 'gemini', baseURL: 'https://generativelanguage.googleapis.com/v1beta', apiKeyEnv: 'GEMINI_API_KEY', format: 'gemini', isFree: true },
  { name: 'github', baseURL: 'https://models.github.ai/inference', apiKeyEnv: 'GITHUB_MODELS_API_KEY', format: 'openai', isFree: true },
  { name: 'mistral', baseURL: 'https://api.mistral.ai/v1', apiKeyEnv: 'MISTRAL_API_KEY', format: 'openai', isFree: true },
  { name: 'cerebras', baseURL: 'https://api.cerebras.ai/v1', apiKeyEnv: 'CEREBRAS_API_KEY', format: 'openai', isFree: true },
  { name: 'sambanova', baseURL: 'https://api.sambanova.ai/v1', apiKeyEnv: 'SAMBANOVA_API_KEY', format: 'openai', isFree: true }
];
```

---

### 3.2 配置层单独补 key 管理

`src/config.ts` 里把这些 key 都加进去，`getAllProviderKeysStatus()` 也跟着扩。

```ts
const PROVIDER_ENV_MAP: Record<string, string> = {
  openrouter: 'OPENROUTER_API_KEY',
  groq: 'GROQ_API_KEY',
  opencode: 'OPENCODE_API_KEY',
  gemini: 'GEMINI_API_KEY',
  github: 'GITHUB_MODELS_API_KEY',
  mistral: 'MISTRAL_API_KEY',
  cerebras: 'CEREBRAS_API_KEY',
  sambanova: 'SAMBANOVA_API_KEY'
};
```

重点：
- 不要把不同 provider 的 key 校验混成同一个逻辑。
- 哪个 provider 需要特殊格式，就单独处理。

---

### 3.3 UI 先显示完整供应商卡片

页面先把 8 个 provider 都显示出来，不等后端统一完美。

```ts
const providers = [
  'openrouter', 'groq', 'opencode', 'gemini',
  'github', 'mistral', 'cerebras', 'sambanova'
];
```

每个卡片展示：
- 名称
- key 状态
- 获取地址
- 独立“验证”按钮

---

## 4. 每个 provider 的独立接入方案

### 4.1 Gemini

特点：
- 官方模型名带 `models/` 前缀
- 需要单独做模型名规范化
- `generateContent` 和 OpenAI 风格不完全一致时，保留独立逻辑

关键片段：

```ts
function normalizeGeminiModelId(modelId: string): string {
  return modelId.startsWith('models/') ? modelId : `models/${modelId}`;
}
```

验证策略：
- 先 `GET /models`
- 再对 `gemini-3.1-flash-lite-preview` 做最小 `generateContent`

---

### 4.2 GitHub Models

特点：
- 路径和模型命名可能与 OpenAI 接口相近
- 但模型 id 可能需要单独清洗
- 这次优先接入 GitHub Models 的免费模型，key 直接参考 `.env` 里的 `GITHUB_MODELS_API_KEY`

建议：
- 先独立写 `github` provider 适配
- 先验证 `models` 拉取是否稳定
- 再接最小 chat 调用

---

### 4.3 Mistral

特点：
- OpenAI 兼容度高，但不要默认完全一致
- 先按独立 provider 处理

建议：
- 独立 key 校验
- 独立模型发现
- 独立 fallback 标签

---

### 4.4 Cerebras

特点：
- 可能模型少，但速度快
- 先独立接入，不要提前合并到统一 provider 逻辑

---

### 4.5 SambaNova

特点：
- 接口和模型可用性可能有自己的限制
- 先独立验证最小调用

---

## 5. 路由层改造

不要在 `server.ts` 里继续堆大分支，先做“每 provider 一个执行器”。

```ts
type ProviderExecutor = {
  validateKey: (apiKey: string) => Promise<boolean>;
  listModels: (apiKey: string) => Promise<Model[]>;
  chat: (apiKey: string, body: unknown) => Promise<Response>;
};
```

不是统一抽象成一个大工厂，而是：
- 每个 provider 有自己的 executor 文件
- `server.ts` 只负责选中 provider 然后调用对应 executor

示意：

```ts
const executor = getProviderExecutor(provider);
const ok = await executor.validateKey(apiKey);
```

---

## 6. fallback 策略

先不做“全 provider 统一评分模型”。

阶段 1：
- 每个 provider 只要能返回可用模型就算成功
- fallback 只按可用性和失败历史排序

阶段 2：
- 再考虑是否把一些共性逻辑合并

关键点：
- Gemini / GitHub Models / Mistral / Cerebras / SambaNova 不强行共用同一套评分规则

---

## 7. 验收顺序

按这个顺序推进：

1. `PROVIDERS` 扩展到 8 个
2. `.env` / key 状态显示完整
3. 每个 provider 都能单独验证 key
4. 每个 provider 至少能拉到模型列表
5. 每个 provider 至少能跑通一个最小调用
6. 每个 provider 至少有 1 个 smoke test，验证模型调用成功
7. UI 能看到 8 个供应商
8. 再考虑 fallback 和统一化

---

## 8. 暂不做的事

- 不提前做统一 provider adapter
- 不提前合并成同一个 chat 请求路径
- 不提前做数据库
- 不提前做复杂权限系统

---

## 9. TODO 列表

### 阶段 1：打通基础接入

- [ ] 扩展 `PROVIDERS` 注册表，加入 `gemini` / `github` / `mistral` / `cerebras` / `sambanova`
- [ ] 扩展 `PROVIDER_ENV_MAP` 和 `getAllProviderKeysStatus()`
- [ ] 更新 UI，显示 8 个供应商卡片和独立 key 状态
- [ ] 为每个 provider 补独立验证入口

### 阶段 2：独立 provider 逻辑

- [ ] 为 `gemini` 编写独立模型名规范化和最小调用验证
- [ ] 为 `github` 编写独立模型拉取和最小调用验证
- [ ] 为 `mistral` 编写独立 key 校验、模型拉取和最小调用验证
- [ ] 为 `cerebras` 编写独立 key 校验、模型拉取和最小调用验证
- [ ] 为 `sambanova` 编写独立 key 校验、模型拉取和最小调用验证

### 阶段 3：路由与 fallback

- [ ] 为每个 provider 拆出独立 executor
- [ ] 让 `server.ts` 只负责选择 provider 并转发
- [ ] 保留 provider 专属 fallback 规则，不强行统一评分

### 阶段 4：测试与验收

- [ ] 为每个 provider 增加至少 1 个 smoke test
- [ ] 确认每个 provider 都能返回模型列表
- [ ] 确认每个 provider 都能完成一次最小调用
- [ ] 确认 UI / API / 测试结果一致
- [ ] 再决定哪些逻辑可以合并重构

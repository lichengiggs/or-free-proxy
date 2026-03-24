# models.dev 本地字典开发蓝图

需求源
- 唯一需求源为仓库根的 `spec.md`。
- 本文只展开 `spec.md` 已确认的需求，不引入额外产品假设。

## 1. Architecture & Design

### 1.1 目标
- 将 `https://models.dev/` 的模型信息固化为本地 JSON 字典，供服务离线读取。
- 启动时优先读取本地缓存，并在后台异步更新，不阻塞服务启动。
- 通过硬过滤 + 家族分层 + 轻量排序，把更可能的优质模型放到前面，同时保持实现简单可维护。

### 1.2 模块设计
- `scripts/update-models.js`
  - 职责：抓取、解析、标准化、过滤、分层排序、原子写入本地字典。
- `src/model-dictionary.ts`
  - 职责：加载本地字典、暴露读取接口、触发后台更新、封装失败回退。
- `src/server.ts`
  - 职责：服务启动时调用字典加载与后台更新入口。
- `data/models.dev.json`
  - 职责：本地离线字典主文件。
- `data/models.dev.json.bak.*`
  - 职责：更新前备份，保障可回滚。

### 1.3 数据流
1. 服务启动。
2. `src/model-dictionary.ts` 先读取 `data/models.dev.json`。
3. 若文件存在，立即提供给后续模型选择逻辑使用。
4. 同时后台触发 `scripts/update-models.js` 的更新流程。
5. 更新脚本从 `models.dev` 获取原始数据。
6. 解析出标准字段并保留 `raw`。
7. 执行硬过滤：
   - 若 `params_b` 可明确解析或可被保守推断，且 `< 10`，则直接过滤
  - 若 `params_b` 可明确解析或可被保守推断，且 `>= 10`，则正常保留
  - 若参数量无法可靠判断，则保留条目并标注 `field_missing: true`（参数未知不做惩罚性淘汰）
   - `release_year >= 2025`
   - `tool_support_flag === true`
   - 若同时存在 `input_context_limit` 与 `output_context_limit`，则必须满足 `input_context_limit >= 100000` 且 `output_context_limit >= 10000`
   - 若上下文字段缺失，保留条目但标注 `field_missing: true`
8. 执行分层与排序：
  - 先按家族分层：`Tier A`（已验证主流家族）与 `Tier B`（其余模型）
  - 层内按三字段排序：`context能力`、`release_month`、`params_b(可用时)`
9. 原子写入新字典文件，更新 `updated_at`、`tier`、`rank`。
10. 若任一步失败，保留旧字典并记录错误。

### 1.4 接口定义

#### 内部更新入口
```ts
type ModelDictionaryEntry = {
  id: string
  name: string
  tier: 'A' | 'B'
  params_b: number | null
  input_context_limit: number | null
  output_context_limit: number | null
  release_year: number | null
  release_at?: string | null
  license?: string | null
  url?: string | null
  tags: string[]
  source: 'models.dev'
  tool_support_flag: boolean
  field_missing?: boolean
  rank: number
  updated_at: string
  raw: unknown
}

type ModelDictionaryFile = {
  updated_at: string
  models: ModelDictionaryEntry[]
}

async function updateModelsDictionary(): Promise<{
  success: boolean
  updated: boolean
  path: string
  count?: number
  error?: string
}>
```

#### 服务侧加载入口
```ts
async function loadModelDictionary(): Promise<ModelDictionaryFile | null>
async function triggerBackgroundDictionaryUpdate(): Promise<void>
```

## 2. Core Snippets

### 2.1 抓取 + 标准化伪代码
```js
async function fetchModelsDevWithRetry() {
  const delays = [1000, 2000, 4000]

  for (let i = 0; i < delays.length; i += 1) {
    try {
      const res = await fetch(MODELS_DEV_URL, { signal: AbortSignal.timeout(10000) })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      return await parseModelsDevResponse(res)
    } catch (error) {
      if (i === delays.length - 1) throw error
      await sleep(delays[i])
    }
  }
}

function normalizeEntry(rawItem) {
  return {
    id: buildCompositeId(rawItem.provider_id, rawItem.model_id),
    name: rawItem.name || rawItem.model_id,
    params_b: normalizeParamsToB(rawItem.parameters, rawItem.model_id, rawItem.name),
    input_context_limit: normalizeNumber(rawItem.input_context_limit),
    output_context_limit: normalizeNumber(rawItem.output_context_limit),
    release_year: normalizeReleaseYear(rawItem.release_date),
    release_at: normalizeReleaseAt(rawItem.release_date),
    license: rawItem.license || null,
    url: rawItem.url || null,
    tags: normalizeTags(rawItem.tags),
    source: 'models.dev',
    tool_support_flag: detectToolSupport(rawItem),
    raw: rawItem
  }
}
```

### 2.2 过滤逻辑伪代码
```js
function applyHardRules(entry) {
  if (entry.params_b != null && entry.params_b < 10) return { keep: false }
  if (entry.release_year == null || entry.release_year < 2025) return { keep: false }
  if (!entry.tool_support_flag) return { keep: false }

  const hasContext =
    typeof entry.input_context_limit === 'number' &&
    typeof entry.output_context_limit === 'number'

  if (!hasContext) {
    return {
      keep: true,
      field_missing: true
    }
  }

  if (entry.input_context_limit < 100000) return { keep: false }
  if (entry.output_context_limit < 10000) return { keep: false }

  return { keep: true, field_missing: false }
}
```

### 2.3 分层排序伪代码
```js
const TIER_A_FAMILIES = [
  'gpt',
  'claude',
  'gemini',
  'deepseek',
  'minimax',
  'kimi',
  'glm',
  'mimo',
  'step'

]

const FAMILY_ALIAS = {
  'gpt-5': 'gpt',
  'chatgpt': 'gpt',
  'MiniMax': 'minimax',
  'moonshot': 'kimi',
  'kimi-k2': 'kimi'
}

const TIER_A_FAMILY_SET = new Set(
  TIER_A_FAMILIES.map((x) => x.toLowerCase())
)

function normalizeFamily(value) {
  return String(value || '').trim().toLowerCase()
}

function detectFamily(entry) {
  const baseFamily = normalizeFamily(entry.family)
  if (baseFamily) {
    const alias = normalizeFamily(FAMILY_ALIAS[baseFamily] || baseFamily)
    if (alias) return alias
  }

  // family 缺失时，从 id/name 做保守识别；统一小写后匹配，避免大小写导致漏识别
  const haystack = `${entry.id || ''} ${entry.name || ''}`.toLowerCase()
  if (haystack.includes('minimax')) return 'minimax'
  if (haystack.includes('gpt')) return 'gpt'
  if (haystack.includes('claude')) return 'claude'
  if (haystack.includes('gemini')) return 'gemini'
  if (haystack.includes('deepseek')) return 'deepseek'
  if (haystack.includes('kimi') || haystack.includes('moonshot')) return 'kimi'
  if (haystack.includes('glm')) return 'glm'
  if (haystack.includes('mimo')) return 'mimo'
  if (haystack.includes('step')) return 'step'

  return ''
}

function buildTier(entry) {
  const family = detectFamily(entry)
  return TIER_A_FAMILY_SET.has(family) ? 'A' : 'B'
}

function computeContextScore(entry) {
  if (entry.input_context_limit == null || entry.output_context_limit == null) return 0
  return entry.input_context_limit + entry.output_context_limit
}

function sortEntries(entries) {
  return [...entries].sort((a, b) => {
    if (a.tier !== b.tier) return a.tier === 'A' ? -1 : 1

    const ctxDiff = computeContextScore(b) - computeContextScore(a)
    if (ctxDiff !== 0) return ctxDiff

    const monthA = toReleaseMonthIndex(a.release_at, a.release_year)
    const monthB = toReleaseMonthIndex(b.release_at, b.release_year)
    if (monthA !== monthB) return monthB - monthA

    // 参数仅在可解析时用于打破平局；未知参数不惩罚
    return (b.params_b ?? -1) - (a.params_b ?? -1)
  })
}
```

### 2.4 策略细则（简化版）
- 2026-03-24 快速 demo 结论：基于 `https://models.dev/api.json` 实测 `3876` 条模型里，`parameters/weights/size` 等显式参数字段命中率约 `0%`，仅靠名称正则可推断约 `29.10%`，其余约 `70.90%` 无法可靠判定；`minimax` 与 `gpt-5-mini` 样本均未拿到可用参数。
- 因此 v1 采用简化策略：
  1. 只对“明确小模型（<10B）”做硬过滤；参数未知保留。
  2. 先做家族分层（Tier A/Tier B），不做复杂大权重打分。
  3. 层内仅按 `context`、`release_month`、`params_b(可用时)` 排序。
- 不采用“硬编码具体模型名直接给高分”的策略；最多允许维护一个很小的显式小模型拒绝名单，仅用于已知误判案例。

### 2.5 原子写入伪代码
```js
async function writeDictionaryAtomically(file) {
  const targetPath = 'data/models.dev.json'
  const tmpPath = `${targetPath}.tmp`
  const backupPath = `${targetPath}.bak.${Date.now()}`

  if (await exists(targetPath)) {
    await copyFile(targetPath, backupPath)
  }

  await writeFile(tmpPath, JSON.stringify(file, null, 2))
  await rename(tmpPath, targetPath)
}
```

## 3. Implementation Details

### 3.1 新增文件
- `scripts/update-models.js`
  - 调度入口。
  - 负责抓取、解析、过滤、分层排序、写盘。
- `src/model-dictionary.ts`
  - 负责加载本地字典、缓存、后台更新入口。
- `__tests__/model-dictionary.test.ts`
  - 覆盖解析、过滤、分层排序、回退逻辑。
- `data/models.dev.json`
  - 初始样本或首次生成结果。

### 3.2 修改文件
- `package.json`
  - 增加脚本：`update-models`。
- `src/server.ts`
  - 启动时调用本地字典加载。
  - 在不阻塞启动的前提下触发后台更新。
- `src/fallback.ts` 或当前模型筛选入口文件
  - 将模型候选来源切换为本地字典优先。
  - 确保展示与实际使用的候选集一致。

### 3.3 建议脚本定义
```json
{
  "scripts": {
    "update-models": "node scripts/update-models.js"
  }
}
```

### 3.4 字典文件结构
```json
{
  "updated_at": "2026-03-24T00:00:00.000Z",
  "models": [
    {
      "id": "provider/model",
      "name": "Model Name",
      "params_b": 70,
      "input_context_limit": 128000,
      "output_context_limit": 16000,
      "release_year": 2025,
      "license": "apache-2.0",
      "url": "https://models.dev/...",
      "tags": ["tool-call"],
      "source": "models.dev",
      "tier": "A",
      "tool_support_flag": true,
      "field_missing": false,
      "rank": 1,
      "updated_at": "2026-03-24T00:00:00.000Z",
      "raw": {}
    }
  ]
}
```

## 4. Edge Cases & Error Handling

### 4.1 网络失败
- 请求超时：单次 10s。
- 重试：3 次，延迟 1s / 2s / 4s。
- 最终失败：不覆盖旧文件，只记录错误日志。

### 4.2 models.dev 数据结构变化
- 若 API/页面结构变化导致解析失败：
  - 记录解析错误。
  - 返回更新失败。
  - 保留旧字典。
- 抓取策略分两层：
  - 第一层：优先使用普通 HTTP 抓取/解析，保证 `npm start` 的后台更新足够轻；
  - 第二层：如果页面变成强依赖前端渲染、普通抓取长期失效，则不在服务启动时引入浏览器抓取，而是改为“发布阶段或管理员手动执行 Playwright/无头浏览器脚本，生成本地快照” 的离线更新模式。
- 浏览器抓取只作为兜底更新方案，不进入日常启动链路。

### 4.3 条目字段缺失
- 缺发布日期、tool 支持：直接淘汰。
- 缺参数：不直接淘汰，按“参数未知保留”处理。
- 缺 `input_context_limit` 或 `output_context_limit`：
  - 条目保留。
  - `field_missing: true`。
  - 层内排序时 `context` 按 `0` 处理。
- 缺参数量且无法从模型名保守推断：
  - 条目保留。
  - `field_missing: true`。
  - 层内排序时参数只用于平局，不做惩罚性降权。
  - 只有在参数量被明确识别为 `< 10B` 时才过滤，不因为“未知”直接过滤。

### 4.4 数据为空
- 若抓取结果为空或过滤后为空：
  - 判定为异常更新。
  - 不写空文件覆盖旧文件。
  - 日志记录 `empty_result`。

### 4.5 重复模型
- 唯一键使用 `provider_id + model_id`。
- 若存在重复项：保留信息更完整的一条；若完整度相同，保留最新抓取的一条。

### 4.6 文件写入异常
- 使用临时文件 + rename 保证原子写入。
- 写入失败时清理 `.tmp` 文件。
- 旧文件保持不变。

### 4.7 排序异常
- 若原始字段是字符串但无法映射成数字：
  - `parameters` / `release_date` 解析失败：直接淘汰；
  - `input_context_limit` / `output_context_limit` 解析失败：标注 `field_missing: true`，并按 `0` 参与层内排序。
- 若字段都相同导致排序平局：
  - 按 `provider_id + model_id` 进行稳定字典序排序，保证结果可复现。

## 5. Verification Plan

### 5.1 命令验证
- 生成字典：`npm run update-models`
- 单元测试：`npm test`
- 类型检查：`npx tsc --noEmit`
- 启动服务：`npm start`

### 5.2 验证点
- `data/models.dev.json` 存在。
- 文件中所有条目包含 `spec.md` 要求字段。
- 过滤规则符合：
  - 已明确识别为小于 10B 的模型不存在。
  - 参数未知但其他条件合格的模型会被保留，并带 `field_missing: true`。
  - 非 2025+ 模型不存在。
  - 不支持 tool call 的模型不存在。
- 缺上下文字段的条目带 `field_missing: true`。
- 排序结果先按 `tier(A->B)`，再按 `context`、`release_month`、`params_b(可用时)`，且 `rank` 连续。
- 参数未知条目不会因为缺参数被直接排到末尾。
- 使用字符串输入样本时，`params_b`、`input_context_limit`、`output_context_limit`、`release_year` 都能被稳定映射到数字或触发预期降级。
- 服务启动时即使更新失败也能正常启动。

## 6. PM Review Note

给产品经理的大白话：

- 这套方案先把 `models.dev` 变成你能离线用的本地字典，所以用户选模型时不需要每次都在线扫一遍。
- 它先按你定死的门槛把明显不该展示的小模型、老模型、没 tool call 的模型砍掉。
- 上下文能力只认 `input_context_limit` 和 `output_context_limit` 这两个明确字段，避免再被模糊字段带偏。
- 真正排序时，不走复杂大权重公式，而是“家族分层 + 三字段排序”，更易维护也更稳定。
- 启动时先读旧字典，后台再更新，所以不会把服务卡住；更新失败也不会把现有可用数据冲掉。
- 这样 `spec.md` 里的 5 条验收标准都被一一落地了：文件结构、过滤规则、可复现排序、启动容错、可审计字段，全都有对应实现点和验证方法。

## 7. Atomic Todo List

- [x] 1. 环境/配置准备：确认 `spec.md` 为唯一需求源并锁定输出路径为 `data/models.dev.json`
- [x] 1. 环境/配置准备：在 `package.json` 增加 `update-models` 脚本定义
- [x] 1. 环境/配置准备：创建 `data/` 目录并约定备份文件命名规则
- [x] 2. 核心逻辑开发：新增 `scripts/update-models.js` 抓取 `models.dev` 原始数据
- [x] 2. 核心逻辑开发：实现原始数据解析与标准字段归一化
- [x] 2. 核心逻辑开发：实现 `provider_id+model_id` 复合唯一键生成逻辑
- [x] 2. 核心逻辑开发：实现参数 / 发布时间 / tool 支持硬过滤逻辑
- [x] 2. 核心逻辑开发：实现参数字段缺失时的保守推断逻辑与已知小模型拒绝名单机制
- [x] 2. 核心逻辑开发：实现家族识别与 `tier(A/B)` 分层逻辑（小规模 alias 表）
- [x] 2. 核心逻辑开发：实现层内三字段排序（context、release_month、params_b可用时）
- [x] 2. 核心逻辑开发：实现参数未知中性处理与稳定平局规则
- [x] 2. 核心逻辑开发：实现 `raw`、`tier`、`updated_at`、`rank` 字段写入逻辑
- [x] 2. 核心逻辑开发：实现原子写入与备份回滚逻辑
- [x] 2. 核心逻辑开发：实现 3 次重试、10 秒超时、失败保留旧文件逻辑
- [x] 3. 接口/UI 适配：新增 `src/model-dictionary.ts` 封装本地字典加载接口
- [x] 3. 接口/UI 适配：在 `src/server.ts` 启动流程中接入本地字典加载与后台异步更新
- [x] 3. 接口/UI 适配：将模型候选读取逻辑切换为本地字典优先
- [x] 4. 测试验证：新增 `__tests__/model-dictionary.test.ts` 覆盖解析与硬过滤逻辑
- [x] 4. 测试验证：新增测试覆盖 tier 分层、层内排序、稳定平局与 `rank` 连续编号
- [x] 4. 测试验证：新增测试覆盖参数未知保留、明确小模型过滤逻辑
- [x] 4. 测试验证：新增测试覆盖网络失败、空结果、写入失败回退逻辑
- [x] 4. 测试验证：运行 `npm run update-models` 并检查 `data/models.dev.json` 输出结构
- [x] 4. 测试验证：运行 `npm test`、`npx tsc --noEmit`、`npm start`
- [x] 5. 临时文件清理：清理更新过程产生的 `.tmp` 文件并保留必要备份

## 8. Revision Log

- 策略收敛为“硬过滤 + 家族分层 + 三字段排序”，移除复杂加权评分与归一化计算。
- 基于 `models.dev/api.json` 快速 demo 实测，确认参数字段缺失占比高，采用“参数未知保留、仅明确小模型过滤”的生产策略。
- 补充 Tier A/Tier B 与稳定排序规则，确保结果可解释、可复现、低维护成本。

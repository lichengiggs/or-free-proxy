# or_free_proxy 深度学习与发现报告

## 1. 项目定位与目标

这是一个本地运行的「OpenAI 兼容代理」，目标不是做统一计费或统一鉴权，而是解决一个非常具体的问题：

- 免费模型很多，但**可用性不稳定**（限流、临时下线、区域网络问题）
- 用户不想每次手动切换模型和 provider
- 希望客户端（OpenClaw / Cursor / Continue）始终只连一个固定本地地址

该项目通过 `http://localhost:8765/v1` 提供 OpenAI 风格接口，在内部做多 provider 模型发现 + 失败回退。

---

## 2. 技术栈与工程形态

- 后端框架：`hono` + `@hono/node-server`
- 语言：TypeScript（ESM）
- 运行方式：`tsx src/server.ts`
- 测试：Jest + ts-jest（ESM 模式）
- 网络层：原生 `fetch` + `undici`（支持代理）
- 前端：单文件 `public/index.html`（原生 HTML/CSS/JS，无打包）

工程形态是典型轻量化工具：

- 无数据库
- 本地文件持久化（`.env`, `config.json`, `rate-limit-state.json`）
- 单进程内存状态辅助（模型可用性 Map、配置缓存等）

---

## 3. 目录与模块职责

### 3.1 核心目录

- `src/server.ts`：HTTP 路由入口，代理请求与管理 API
- `src/config.ts`：配置读写、环境变量、API Key 管理、带超时请求封装
- `src/models.ts`：模型拉取、免费过滤、评分排序（含多 provider 拉取）
- `src/fallback.ts`：模型回退链构建 + 执行器
- `src/rate-limit.ts`：限流状态持久化与冷却判断
- `src/openclaw-config.ts`：检测/合并/备份/恢复 OpenClaw 配置
- `src/providers/*`：provider 注册表与抽象（当前只部分接入）
- `public/index.html`：管理 UI（配置 key、选模型、配置 OpenClaw）

### 3.2 其他模块状态

- `src/candidate-pool.ts`：实现了候选模型池与主动验证，但**当前主流程未使用**
- `src/providers/router.ts`、`src/providers/adapters/openai.ts`：有抽象层，但 `server.ts` 目前走自定义流程，未复用 router

结论：项目有一部分“已上线主路径”和一部分“演进中的抽象层”，存在代码路径分叉。

---

## 4. 端到端工作原理（请求路径）

## 4.1 启动

`npm start` -> `src/server.ts` 启动 Hono 服务：

- 配置 CORS
- 挂载静态页面（`public/index.html`）
- 暴露 `/v1/chat/completions` 与一组 `/admin/*`、`/api/*` 管理接口

## 4.2 模型调用主链

客户端请求 `/v1/chat/completions` 后，核心流程：

1. 读取当前默认模型（`config.default_model`）
2. 调用 `executeWithFallback(...)`
3. `fallback.ts` 生成回退链：
   - 首先放入首选模型
   - 再动态拉取所有 provider 可用模型并按评分排序
   - 最后保证 `openrouter/auto:free` 在链尾
4. 逐个尝试模型：
   - 429/503 失败会写入 rate-limit 状态
   - 命中成功立即返回
5. 响应附加诊断头：
   - `X-Actual-Model`
   - `X-Fallback-Used`
   - `X-Fallback-Reason`

## 4.3 provider 解析规则

- 模型 ID 形如 `openrouter/xxx`、`groq/xxx`、`opencode/xxx` 时按前缀路由
- 否则默认按 openrouter 处理

这让前端可直接选择“带 provider 前缀”的模型，实现跨 provider 透明切换。

---

## 5. 核心模块拆解

## 5.1 配置与密钥管理（`src/config.ts`）

### 做得好的点

- `getConfig()`：首次无 `config.json` 时自动写默认配置
- `setConfig()`：增量合并后落盘
- `saveProviderKey()`：使用 `writeLock` 串行写 `.env`，避免并发覆写
- `maskApiKey()`：按 key 前缀差异化掩码（`sk-or-`、`gsk-` 等）
- `fetchWithTimeout()`：内置超时与代理支持（`HTTP_PROXY` / `HTTPS_PROXY`）

### 需要注意的点

- `ENV` 是模块加载时快照，不是实时读取 `process.env`；部分状态读取会“旧值”
- `saveApiKey()`（旧接口）没有复用写锁
- `.env` 写入未显式设置文件权限（测试里有权限预期）

## 5.2 模型拉取与评分（`src/models.ts`）

主要能力：

- `fetchModels()`：OpenRouter 模型拉取 + 1 小时缓存
- `fetchAllModels()`：按已配置 key 遍历 provider 拉取 `/models`，并统一成 `provider/model` ID
- 免费过滤策略：
  - 常规：`prompt=0` 且 `completion=0`
  - OpenCode：另有 `-free` 后缀规则（在其他模块重复实现）
- 排序维度：
  - 上下文长度（最高 40）
  - 可信 provider（最高 30）
  - 参数规模（最高 20）

## 5.3 回退执行（`src/fallback.ts`）

这是项目最关键模块，解决“免费模型波动”问题：

- 结合三种状态：
  1) 动态可用性（内存 `modelAvailability`）
  2) 速率限制持久化状态（`rate-limit.ts`）
  3) 实时请求结果（429/503/其他失败）
- 首选失败时自动尝试候选链
- 会记录尝试轨迹（`attempted_models`）并告知 fallback 原因

设计取舍：

- 简洁有效，优先“尽快拿到一个可用回答”
- 不做复杂熔断窗口/统计学习，维护成本低

## 5.4 限流状态（`src/rate-limit.ts`）

- 文件：`rate-limit-state.json`
- 结构：按模型 ID 存 `limited_at`、`retry_after`、`reason`
- 冷却策略：固定 30 分钟
- 支持清理过期记录

价值：跨进程重启仍保留短期“失败记忆”，避免重复撞同一限流模型。

## 5.5 OpenClaw 配置集成（`src/openclaw-config.ts`）

能力：

- 自动定位：`~/.openclaw/openclaw.json`
- 检测存在性和 JSON 有效性
- 修改前自动备份
- 合并注入 `free_proxy` provider 和 `free_proxy/auto` 模型
- 支持列出备份、从备份恢复

该模块的核心价值是降低手工配置成本，符合“个人工具”定位。

---

## 6. HTTP 接口清单与行为细节

### 6.1 代理接口

- `POST /v1/chat/completions`
  - 输入：OpenAI 格式 body
  - 输出：上游原始 JSON/流式响应
  - 额外头：`X-Actual-Model`、`X-Fallback-Used`、`X-Fallback-Reason`

### 6.2 管理模型

- `GET /admin/models`
  - 拉取所有已配置 provider 的免费模型（当前不做逐个可用性验证）
- `PUT /admin/model`
  - 设置默认模型到 `config.json`

### 6.3 密钥管理

- `GET /api/provider-keys`
  - 返回 openrouter/groq/opencode 配置状态（已掩码）
- `POST /api/provider-keys`
  - 先调用对应 provider `/models` 验证，再写入 `.env`

兼容旧接口（偏 OpenRouter 单 provider）：

- `POST /api/validate-key`
- `GET /api/validate-key`

### 6.4 OpenClaw 管理

- `GET /api/detect-openclaw`
- `POST /api/configure-openclaw`
- `GET /api/backups`
- `POST /api/restore-backup`

---

## 7. 前端页面（`public/index.html`）工作机制

页面是三步流程：

1. 配置 provider key（OpenRouter/Groq/OpenCode）
2. 拉取并筛选模型，支持按 provider tab 切换
3. 自动配置 OpenClaw，并可查看/恢复备份

前端特点：

- 纯原生 JS，状态集中在少量全局变量（`allModels`, `currentProviderFilter`）
- 关键操作均有按钮 loading 态和 toast 提示
- 模型选择后做本地 UI 更新，不重复请求模型列表（体验更快）

---

## 8. 测试覆盖现状与一致性评估

测试文件较多（配置、模型、fallback、provider、openclaw、API 路由），但当前存在明显“实现-测试漂移”。

我本地执行 `npm test -- --runInBand` 的结果：

- 14 个测试套件中 4 个失败
- 127 个用例中 35 个失败

核心漂移点：

1. **掩码规则变化**
   - 实现：`sk-***456`
   - 部分测试仍期望：`sk-****456`

2. **OpenClaw 备份文件名模式变化**
   - 实现使用：`openclaw.bakN`
   - 多个测试仍按：`openclaw.json.backup.timestamp`

3. **不存在的导出被测试引用**
   - `__tests__/models.new.test.ts` 依赖 `getModels`，但 `src/models.ts` 并未导出

4. **路由语义变化导致断言过期**
   - 例如 `/api/validate-key` 错误文案、状态码期望与当前实现不一致

5. **测试环境清理逻辑不兼容当前产物**
   - 清理 `.openclaw-test` 目录时只删特定文件模式，导致 `rmdir` 失败

结论：测试体系有价值，但目前不能作为“真实回归门禁”，需要先统一协议与命名后修复。

---

## 9. 关键发现（设计优点）

1. **最有价值能力是“失败自动回退”**，不是模型排序本身
2. **多 provider 统一前缀模型 ID** 是正确抽象，兼顾透明与可控
3. **限流状态持久化** 对免费模型场景非常实用
4. **OpenClaw 一键配置 + 备份恢复** 极大降低上手成本
5. **单文件前端 + 轻后端** 部署和维护门槛很低，符合个人工具目标

---

## 10. 关键风险与技术债

1. **代码路径分叉**
   - `ProviderRouter` / `CandidatePool` 已存在但主流程未接入，后续维护可能出现“双实现漂移”

2. **自定义 provider 能力未闭环**
   - 虽支持保存自定义 provider/model 到配置，但 `parseModelId` 和主请求路由只识别内置 provider

3. **`/admin/models?refresh=true` 参数未实际生效**
   - 前端有刷新按钮，但后端未用 query 强制刷新路径

4. **OpenClaw 配置前置校验仍偏旧逻辑**
   - `/api/configure-openclaw` 只检查 OpenRouter key 状态，不完全匹配“多 provider 任一可用即可”

5. **安全细节仍可增强**
   - `.env` 权限未显式收紧
   - `config.json` 存储自定义 provider 的明文 key（如使用该功能）

---

## 11. 建议的最小改进路径（按优先级）

### P0（先恢复可信回归）

- 统一备份文件命名规范（实现与测试择一）
- 删除或修复 `models.new.test.ts` 对 `getModels` 的无效依赖
- 修复掩码规则断言与当前实现不一致问题

### P1（提升主流程一致性）

- `/api/configure-openclaw` 改为“任一 provider key 已配置即可”
- `/admin/models` 真正支持 `refresh=true` 强刷
- 将免费模型过滤逻辑收敛到单一函数，避免多处复制

### P2（降低长期维护成本）

- 明确是否正式启用 `ProviderRouter` / `CandidatePool`
  - 要么接入主链
  - 要么移除，减少认知负担

---

## 12. 总结

这个项目的本质不是“模型平台”，而是一个针对免费模型不稳定场景的**本地可用性增强层**。其核心竞争力在于：

- OpenAI 兼容入口固定
- 多 provider 聚合
- 自动 fallback + 限流记忆
- 客户端（尤其 OpenClaw）低成本接入

从工程角度看，主体架构已经可用，且设计方向正确；当前主要问题不在核心思路，而在“演进过程中接口与测试未同步”带来的一致性风险。只要先修复 P0/P1 项，整体会从“可用工具”快速进入“稳定可维护工具”状态。

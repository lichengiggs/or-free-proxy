# or_free_proxy 重构计划（可维护性 + 小白体验）

## 1. 目标与验收标准

本次重构只做两件事：

1. **让代码好维护**：结构清晰、职责单一、测试可作为回归门禁。
2. **让小白用户更好用**：安装后按向导操作，遇到问题能看懂、能自救。

### 量化验收（建议）

- `npm test` 全绿，关键路径覆盖率 >= 80%
- 新用户首次配置成功率 >= 90%（按本地引导流程）
- 常见错误（无 key、限流、网络失败）都有可读提示与下一步建议
- 配置相关逻辑（`.env`、`config.json`、OpenClaw）全部通过统一服务层

---

## 2. 当前痛点（基于 research）

### 2.1 维护性痛点

- 主链路与抽象层并存但未统一（`server.ts` 直连逻辑 vs `ProviderRouter`/`CandidatePool`）
- 免费模型过滤、provider 规则在多个模块重复
- 测试与实现漂移严重（命名、掩码规则、导出符号、状态码语义）
- 配置写入策略不统一（有写锁和无写锁混用）

### 2.2 用户体验痛点

- 配置步骤虽有 UI，但“当前状态 -> 下一步”不够强引导
- 错误提示偏技术化，缺少“你该怎么做”
- 模型刷新和可用性语义不清晰（列出免费模型 != 保证当前可用）
- OpenClaw 配置逻辑仍偏向旧单 provider 认知
- OpenCode 可用性差：拿到 key 后仍常出现“无可用模型”，缺少可解释的诊断与兜底
- 缺少“手动添加模型”能力：OpenRouter 临时免费模型可能不带 `:free` 且价格字段非 0，当前无法由用户显式加入候选
---

## 3. 重构原则（避免过度工程）

- **KISS/YAGNI**：不引入数据库、不做复杂分布式能力。
- **单一事实来源**：provider 规则、免费过滤、模型评分都只保留一个实现。
- **分层隔离**：路由层只做 HTTP 协议，业务放 service 层。
- **向后兼容优先**：保留现有关键 API 路径，逐步迁移。
- **错误对小白友好**：统一错误码 + 人话文案 + 建议动作。

---

## 4. 目标架构（分层）

建议拆成 4 层：

1. **Routes 层**（HTTP）
   - 只做入参校验、出参格式化、状态码映射。
2. **Services 层**（业务）
   - ChatService / ModelService / ConfigService / OpenClawService / HealthService。
3. **Domain 层**（规则）
   - provider 解析、免费过滤、评分、fallback 策略。
4. **Infra 层**（IO）
   - 文件存储、HTTP 客户端、时钟、日志。

### 目录建议

```txt
src/
  app.ts
  server.ts
  routes/
    chat.ts
    admin.ts
    setup.ts
  services/
    chat-service.ts
    model-service.ts
    config-service.ts
    openclaw-service.ts
    health-service.ts
  domain/
    provider.ts
    model-filter.ts
    model-rank.ts
    fallback-engine.ts
    errors.ts
  infra/
    env-repo.ts
    config-repo.ts
    rate-limit-repo.ts
    http-client.ts
    logger.ts
  types/
    api.ts
```

---

## 5. 后端重构方案

## 5.1 统一 Provider 与模型规则

把 provider 能力集中为一个注册表 + 适配器，不再在 `server.ts` 手写分支。

关键片段（示意）：

```ts
export interface ProviderSpec {
  name: 'openrouter' | 'groq' | 'opencode' | string;
  baseURL: string;
  apiKeyEnv: string;
  supportsFreeTag?: boolean;
  isModelFree(model: ProviderModel): boolean;
}
```

收益：新增 provider 只需加一条 spec，不改主流程。

## 5.2 引入 ChatService（收口主链路）

将 `POST /v1/chat/completions` 的全部逻辑迁移到 `ChatService`：

- 解析目标模型
- 生成 fallback 链
- 执行 provider 调用
- 记录 rate-limit
- 产出 `fallbackInfo`

路由层仅保留：

```ts
const result = await chatService.complete(reqBody, reqHeaders);
return toHttpResponse(result);
```

## 5.3 配置服务统一化

把 `.env` / `config.json` 的读写都放到 `ConfigService`，禁止跨模块直接写文件。

最小要求：

- 全部写入走同一把锁
- `.env` 写入后在非 Windows 系统 `chmod 600`
- 避免 `ENV` 快照读旧值：运行时读取 `process.env`

## 5.4 错误模型标准化

定义统一业务错误码，路由层再映射为 HTTP 状态：

```ts
type AppErrorCode =
  | 'NO_PROVIDER_KEY'
  | 'MODEL_UNAVAILABLE'
  | 'RATE_LIMITED'
  | 'UPSTREAM_TIMEOUT'
  | 'INVALID_INPUT';
```

每个错误返回：`code` + `message` + `hint`。

示例：

- message: `当前模型暂时不可用`
- hint: `请点击“刷新模型”，或改用 auto`

## 5.5 OpenClaw 服务重构

- 继续保持自动检测 + 备份 + 合并 + 恢复。
- 明确备份命名规范（推荐 `openclaw.bak1` 或时间戳二选一），并与测试完全一致。
- 配置前置校验改为：任一可用 provider key 即可，不再绑定 OpenRouter。

## 5.6 OpenCode 可用性专项改造

目标：不是“列表里看起来有模型”，而是“用户能实际调用成功”。

- 增加 `ProviderHealthService`：对每个 provider 做轻量探测（`/models`）+ 实际最小调用探测（`/chat/completions`，`max_tokens=1`）
- OpenCode 模型可用性从“名称/后缀推断”改为“调用验证优先”
- 在 `/admin/models` 中返回每个模型的 `verified` 与 `lastCheckedAt`
- 若 OpenCode 探测失败，返回可读原因（网络不可达 / key 无效 / 模型不可调用）与建议操作

关键片段（示意）：

```ts
type ModelAvailability = {
  id: string;
  provider: string;
  verified: boolean;
  reason?: 'auth_failed' | 'network_error' | 'model_unavailable';
  lastCheckedAt: number;
};
```

## 5.7 手动模型白名单（解决“临时免费模型”）

新增“用户可控候选”机制：允许用户手动添加任意 provider/model，并优先参与 fallback。

- 新增配置项：`config.customModels[]`
- 新增接口：
  - `POST /api/custom-models/verify`：先做最小调用验证
  - `POST /api/custom-models`：保存已验证模型
  - `GET /api/custom-models`、`DELETE /api/custom-models/:id`
- fallback 链策略：`customModels`（按用户顺序）优先于自动发现免费模型
- UI 提供“添加模型 ID”入口，并展示验证结果（可用/不可用 + 原因）

关键片段（示意）：

```ts
interface CustomModelConfig {
  provider: string;
  modelId: string;
  priority: number;
  enabled: boolean;
}
```

---

## 6. 前端体验重构方案（重点）

目标：让小白按“向导”完成配置，减少理解成本。

## 6.1 三段式向导（强引导）

1. **连接供应商**（至少 1 个成功）
2. **选择模式**（推荐 `auto`，高级用户可手选）
3. **连接客户端**（OpenClaw 一键配置 + 验证）

每一步提供状态：`未开始 / 进行中 / 已完成 / 失败`。

## 6.2 新手与高级双模式

- **新手模式（默认）**：只显示必要按钮和推荐路径。
- **高级模式**：显示 provider 明细、模型过滤、原始错误详情。

## 6.3 错误提示升级

统一 UI 提示结构：

- 发生了什么（1 句话）
- 你可以怎么做（最多 2 步）
- 需要等待多久（如限流冷却时间）

示例文案：

- `Groq 当前触发限流，建议 30 分钟后重试；你也可以立即切换到 auto。`

## 6.4 首次使用健康检查

新增“快速自检”按钮，检查：

- 服务是否启动
- 至少一个 key 是否有效
- 是否有可用免费模型
- OpenClaw 配置是否存在且合法
- OpenCode 是否可真实调用（非仅 key 有效）

全部通过后给一条可复制命令：`/model free_proxy/auto`。

## 6.5 新增“手动添加模型”交互

- 入口：模型页增加“手动添加模型”按钮（默认折叠）
- 表单：`provider` + `modelId`
- 流程：先“验证可用性”再“保存到候选”
- 展示：在模型列表中用 `手动` 标签标识，可单独开关启用/禁用
- 文案：明确告诉用户“适合限时免费或价格字段不准确的模型”

---

## 7. 测试与质量门禁重建

## 7.1 测试分层

- **Domain 单测**：免费过滤、排序、fallback 纯逻辑
- **Service 单测**：mock HTTP/文件系统，验证业务语义
- **Route 集成测**：只测协议契约、状态码、返回体
- **E2E 冒烟**：从 key 配置到 `/v1/chat/completions` 成功调用

## 7.2 先修复漂移，再扩展

第一步不是加新测试，而是让现有测试对齐当前协议：

- 掩码规则
- 备份命名
- 不存在的导出引用
- 清理逻辑与真实文件产物一致

## 7.3 CI 门禁（建议）

- `npm test`
- `npx tsc --noEmit`
- 关键 lint（可选）

---

## 8. 实施阶段计划（建议 4 个迭代）

## Phase 1：打地基（1-2 天）

- 建立 `services/domain/infra` 目录
- 抽离 `ConfigService`、`HttpClient`
- 修复测试漂移（不改业务语义）

交付：测试恢复可用，代码结构初步分层。

## Phase 2：主链路迁移（2-3 天）

- `ChatService` 接管 `/v1/chat/completions`
- 合并重复的免费过滤/provider 规则
- 统一错误码与响应结构
- 加入 OpenCode 可用性探测与诊断返回

交付：代理主流程完成服务化，回归测试全绿。

## Phase 3：体验升级（2 天）

- 前端改为向导式流程
- 新手/高级模式开关
- 健康检查与可操作提示
- 增加“手动添加模型”入口与可用性验证流程

交付：小白用户从启动到可用更顺滑。

## Phase 4：收尾与文档（1 天）

- README 重写（5 分钟上手 + FAQ）
- 补充排障文档（限流、网络、OpenClaw）
- 清理未接入的历史代码或正式接入

交付：可维护、可交接、可长期演进。

---

## 9. 风险与回滚策略

### 风险

- 主链路重构时引入行为变化（fallback 顺序、错误码）
- UI 交互改动导致旧用户不适应

### 控制

- 每个 Phase 都保留可运行版本
- 对外接口尽量兼容，必要时增加 `v2` 字段而非直接破坏
- 为关键行为加快照测试（响应头、fallback 信息）

### 回滚

- 保留旧路由实现一段时间（feature flag）
- 若线上本地使用异常，可快速切回旧 Chat 路径

---

## 10. 最小可落地版本（MVP 重构包）

如果希望最快见效，先做这 6 件事：

1. 把主链路迁到 `ChatService`（路由瘦身）
2. 统一 provider/免费过滤规则来源
3. 统一配置读写入口（含权限/锁）
4. 修复所有测试漂移，让 CI 可相信
5. 前端加入“向导 + 健康检查”
6. 重写 README 为小白版

这 6 项完成后，项目维护成本和用户体验都会有明显提升，且不会引入过度工程。

---

## TODO List（执行跟踪）

- [x] T1：统一并收敛配置读写入口（含 `.env` 权限与并发写保护）
- [x] T2：实现 ProviderHealthService（provider 探测 + 模型最小调用验证）
- [x] T3：升级 `/admin/models`（支持 `refresh`、返回 `verified/lastCheckedAt/reason`）
- [x] T4：实现手动模型白名单 API（verify/list/add/delete + priority/enabled）
- [x] T5：升级 fallback 引擎（优先 customModels，并与限流状态协同）
- [x] T6：优化 OpenClaw 配置前置校验（任一 provider key 可用即可）
- [x] T7：前端增加“快速自检”与“手动添加模型”完整流程
- [x] T8：补齐/重构测试（覆盖新增能力，移除漂移用例）
- [x] T9：全量执行 `npm test`，确保测试全绿
- [x] T10：回填文档状态，标记全部任务完成并输出结果

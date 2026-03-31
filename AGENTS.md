# AGENTS.md

## 目标与原则（最小够用）

- 只实现当前明确需求，拒绝过度设计（KISS / YAGNI）。
- 优先可运行、可验证的改动；完成后直接收尾，不扩展无关任务。
- 注释只解释 `Why`，不解释显而易见的 `What`。
- 强制覆盖边界条件：空值、空数组、网络失败、上游异常。

## Python 版关键约定

- `.env` 固定在项目根目录；不要读 home 目录配置。
- 运行与测试统一使用 `uv`：
  - 启动：`uv run free-proxy serve`
  - 测试：`uv run python -m unittest discover -s python_scripts/tests -p 'test_*.py'`
- Provider 接入主入口：
  - 元数据：`python_scripts/provider_catalog.py`
  - 客户端：`python_scripts/client.py`
  - 服务编排：`python_scripts/service.py`
  - 前端卡片：`python_scripts/web/index.html`

## 当前对外兼容面（长期有效）

- OpenAI 兼容接口必须保持：
  - `GET /v1/models`
  - `POST /v1/chat/completions`
- 当前公开稳定模型别名：
  - `free-proxy/auto`
- Python 服务端需要兼容的别名输入：
  - `auto`
  - `free-proxy/auto`
  - `free_proxy/auto`
- Python 服务端仍需识别旧 `coding` 输入：
  - `coding`
  - `free-proxy/coding`
  - `free_proxy/coding`
  - 统一返回 HTTP 400 + `code="model_deprecated"`，不做静默回退。

## OpenClaw / Opencode 配置约定（长期有效）

- OpenClaw 配置写入：
  - 文件：`python_scripts/openclaw_config.py`
  - provider id：`free-proxy`
  - 写入模型：`auto`
  - 若发现旧 `coding` 配置，只做迁移清理，不再写回。

- Opencode 配置写入：
  - 文件：`python_scripts/opencode_config.py`
  - provider id：`free-proxy`
  - 写入模型：`auto`
  - 若发现旧 `coding` 配置，只做迁移清理，不再写回。
  - 文档、示例、验证命令统一使用 `free-proxy/...`。

## Relay 主链路沉淀（长期有效）

- `/v1/chat/completions` 的统一主链路固定为：
  - `python_scripts/request_normalizer.py`
  - `python_scripts/provider_routing.py`
  - `python_scripts/fallback_policy.py`
  - `python_scripts/protocol_converter.py`
  - `python_scripts/response_normalizer.py`
  - `python_scripts/openai_relay.py`
- 责任边界：
  - `server.py` 只做 HTTP 入口、错误映射、结果写回。
  - `openai_relay.py` 是唯一知道“候选尝试 -> fallback -> 最终收敛”的模块。
  - `response_normalizer.py` 负责统一 OpenAI JSON / SSE 输出。
  - `provider_adapter.py` 只做单次上游调用和原始响应包装，不做 fallback。
- `requested_model` 只是内部路由偏好输入，不属于公开稳定模型面；对外文档不要把它写成用户必须理解的主接口。
- `auto` 候选池必须同时考虑：用户指定模型、health、provider hints、静态 fallback；provider `/models` 若不稳定，必须保留 hints 兜底。
- provider 动态列出的候选模型应在该 provider 静态默认候选失败后再懒加载，并立即插入当前 provider 后续位置，不要等所有 provider 都失败后再尝试。

## 本次 Longcat 接入沉淀（长期有效）

- Longcat 走 OpenAI 兼容入口：`https://api.longcat.chat/openai`。
- 新增 provider 时默认评估 `/models` 可用性；若不稳定，必须提供 `model_hints` 兜底，避免 UI 和验证流程卡死。
- 前端不会回填真实 API key；只展示 `configured + masked` 状态（通过 `/api/provider-keys`）。
- 若手工改 `.env` 后服务未重启，可能出现“状态与实际调用不一致”；优先重启后端再验证。

## UI / 验证链路沉淀（长期有效）

- 控制台主流程固定为：先配置 provider，再选推荐模型，最后在同一工作区完成探测与聊天验证；不要再回到“分散多个结果面板”的设计。
- 成功结果只保留一个主展示区，避免“诊断摘要 + 纯正文”重复显示同一份内容。
- 诊断信息必须优先展示可操作字段：`action`、`provider`、`model`、`error`、`category`、`status`、`suggestion`；不要只给一句模糊失败。
- 接入说明、README、页面文案必须统一引用真实稳定接口：`/v1/models`、`/v1/chat/completions`、`free-proxy/auto`。不要把页面内部调试接口如 `/chat/completions` 写进对外文档。
- 遇到“长回复被截断”时，先检查上游请求参数和 provider 返回，尤其是 `max_tokens` / `maxOutputTokens`，不要先假设是前端滚动或 DOM 截断问题。
- `probe` 和真实 `chat` 的输出预算必须分离：探测保持小输出，聊天按 provider 正常输出预算返回正文，避免把探测配置误复用到真实聊天。
- 本地验证 `127.0.0.1` 流式链路时，如果 shell 配了 `http_proxy` / `https_proxy`，必须同时设置 `NO_PROXY=127.0.0.1,localhost` 或临时清空代理变量；否则代理可能注入 `Connection: keep-alive` / `Proxy-Connection: keep-alive`，把已正确结束的 SSE 误判成“服务端没关闭连接”。
- 不要直接启动 opencode 的交互式 TUI 做回归验证；它会占住当前会话。需要验证时优先用非交互模式，例如 `opencode run --format json ...`，或后台命令。

## 测试与发布

- 采用 TDD（red -> green），测试与实现同步提交。
- 提交前最少执行：
  - `uv run python -m unittest discover -s python_scripts/tests -p 'test_*.py'`
  - `npm test`
  - `npx tsc --noEmit`
- 清理中间文档（如 `plan.md`），保留并更新长期文档（`docs/research.md` / README）。运行时学习、探测、健康状态文件只做本地生成，不入库。

## Git 提交规范

- commit message 用英文、小写开头、祈使句，首行只写一件事，不加句号。
- 推荐格式：`<verb> <scope> <intent>`
- 常用动词：`refine`、`fix`、`add`、`remove`、`align`、`document`、`test`
- scope 优先写真实改动面：`python console ui`、`provider routing`、`openclaw config`、`docs`、`tests`
- intent 直接写用户可感知结果或技术结果：`fix chat truncation`、`align sdk docs`、`simplify provider cards`
- 避免空泛 message：`update files`、`misc fixes`、`wip`、`tmp`
- 若同时包含“界面整理 + 缺陷修复”，优先把用户影响更大的结果写进 message，例如：`refine python console ui and fix chat truncation`

## 安全基线

- 禁止提交真实 API key；`.gitignore` 必须覆盖 `.env`。
- 推送前检查：
  - `git status`
  - `git diff --stat`
  - `rg --smart-case "sk-or-|gsk-|ak_|AIza|csk-|ghp_" src __tests__ python_scripts public`
- 发现泄露立刻停止推送，清理提交历史并轮换对应 key。

## 文档维护

- 复杂功能或重构先写执行计划，规范见 `.agent/PLANS.md`。
- 执行计划属于过程文档，任务完成后应清理；结论沉淀到长期文档。
- 用户文档必须优先覆盖三条真实使用路径：
  - OpenAI / Python SDK：`free-proxy/auto`
  - OpenClaw：`free-proxy/auto`
  - Opencode：`free-proxy/auto`

## 工具规范

- 代码搜索必须优先使用 `rg`，并默认带 `--smart-case`；按需加 `--context`。

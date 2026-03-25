# free-proxy 改进方案（面向小白可用 + 可持续维护）

## 1. 背景与目标

基于当前项目现状（Python 后端已具备 provider 探测能力、Node/TS 端已有较完整前端），下一阶段的重点不是“再做一个复杂框架”，而是：

1. 让免费 provider 覆盖更全，且新增成本低。
2. 让免费 model 真正可调用，不只是列表里“看起来有”。
3. 解决 input token 限制导致“可用但不好用”的问题。
4. 统一处理 base URL、path、header、query 差异，减少格式错误。
5. 减少试错耗时，提供“可用模型优先”路径。
6. 给小白一个直观前端：填 key、保存到 .env、一键验证。
7. 保持代码简单，避免维护负担继续上升。

本方案借鉴了两个参考仓库的核心优点：

- free-llm-api-resources：结构化维护 provider/model/limit 信息，强调“真实可用性”和定期更新。
https://github.com/cheahjs/free-llm-api-resources/tree/main
- no-cost-ai：强调入口友好、分类清晰、低门槛使用路径。
https://github.com/zebbern/no-cost-ai
---

## 2. 当前状态评估（你项目里已经有的能力）

### 2.1 Python 侧优势

- 已有统一 provider 抽象（config + client + service）。
- 已支持多 provider 与基础格式分流（OpenAI-like / Gemini）。
- 已有模型探测与候选重试机制雏形。
- 已有 CLI + HTTP API + 单元测试。

### 2.2 主要缺口

1. provider 元数据还偏硬编码，扩展时容易改到多个文件。
2. 缺少“模型可用性状态缓存 + TTL + 失败原因分类”，导致重复试错。
3. 缺少“请求预算与 token 预算策略”（尤其 GitHub/Groq/OpenRouter 免费档）。
4. 缺少“小白向的一体化配置页（后端直接写 .env + 验证反馈）”的 Python 版闭环。
5. 缺少“统一 URL 构造与兼容层”来规避 base/path/query 差异错误。

---

## 3. 总体设计原则

1. 单一职责：provider 元数据、探测逻辑、路由逻辑、配置逻辑分开。
2. 可回退：所有“自动选择”都要保留手工覆盖。
3. 渐进增强：先把可用性做稳，再增加 provider。
4. 小步迭代：每步都能独立上线与回滚。
5. 面向小白：前端默认给出“推荐路径”，隐藏高级参数。

---

## 4. 目标架构（Python 主线）

建议将 Python 方案作为“稳定内核”，Node 端作为参考或过渡。

### 4.1 目录建议

~~~text
python_scripts/
  config.py                  # 环境变量 + provider registry 入口
  provider_catalog.py        # provider 元数据与默认模型候选
  client.py                  # 统一 HTTP 客户端 + 协议适配
  service.py                 # 业务编排（list/probe/chat/select）
  health_store.py            # 可用性缓存（json 文件）
  token_policy.py            # token 预算策略
  server.py                  # API 路由
  cli.py                     # 命令行
  web/
    index.html               # 小白配置页
    app.js                   # 前端逻辑
    style.css                # 样式
~~~

### 4.2 核心运行流

1. 用户在页面填写 key。
2. 后端写入 .env（保留注释和已有键值）。
3. 后端触发 provider key 验证。
4. 验证通过后触发模型探测（并缓存结果）。
5. 页面展示“推荐模型”与“可用/不可用原因”。
6. 真实请求时先走推荐池，失败自动降级。

---

## 5. 可执行改造计划（分三期）

## Phase 1（1-2 天）：稳定性与可维护性打底

### 5.1 Provider 目录化（替代散落硬编码）

新增 provider 元数据中心，减少多处修改。

~~~python
# python_scripts/provider_catalog.py
from dataclasses import dataclass, field
from typing import Literal

FormatType = Literal["openai", "gemini"]

@dataclass(frozen=True)
class ProviderMeta:
    name: str
    base_url: str
    api_key_env: str
    format: FormatType
    model_hints: tuple[str, ...] = field(default_factory=tuple)
    required_query: tuple[tuple[str, str], ...] = field(default_factory=tuple)

PROVIDERS: tuple[ProviderMeta, ...] = (
    ProviderMeta(
        name="openrouter",
        base_url="https://openrouter.ai/api/v1",
        api_key_env="OPENROUTER_API_KEY",
        format="openai",
        model_hints=("openai/gpt-oss-20b:free", "meta-llama/llama-3.3-70b-instruct:free"),
    ),
    ProviderMeta(
        name="github",
        base_url="https://models.github.ai/inference",
        api_key_env="GITHUB_MODELS_API_KEY",
        format="openai",
        model_hints=("gpt-4o-mini", "DeepSeek-V3-0324"),
        required_query=(("api-version", "2024-12-01-preview"),),
    ),
)

PROVIDER_MAP = {p.name: p for p in PROVIDERS}
~~~

收益：新增 provider 只改一个文件，降低维护复杂度。

### 5.2 统一 URL 构造器（降低 base/path/query 错误）

~~~python
# python_scripts/client.py
from urllib.parse import urlencode

def build_url(base_url: str, path: str, query: dict[str, str] | None = None) -> str:
    base = base_url.rstrip("/")
    p = path if path.startswith("/") else f"/{path}"
    if not query:
        return f"{base}{p}"
    return f"{base}{p}?{urlencode(query)}"
~~~

收益：避免 provider 差异带来的 URL 拼接错误。

### 5.3 统一错误分类（减少盲目重试）

将错误归类为 auth、rate_limit、quota、model_not_found、network、unknown。

~~~python
# python_scripts/errors.py
from dataclasses import dataclass

@dataclass
class ProviderFailure:
    category: str
    message: str
    retryable: bool


def classify_error(status: int, body_text: str) -> ProviderFailure:
    text = (body_text or "").lower()
    if status in (401, 403):
        return ProviderFailure("auth", "API Key 无效或权限不足", False)
    if status == 404:
        return ProviderFailure("model_not_found", "模型不存在或路径错误", False)
    if status == 429:
        return ProviderFailure("rate_limit", "触发频率限制", True)
    if status == 402 or "insufficient" in text or "quota" in text:
        return ProviderFailure("quota", "额度不足", False)
    if status >= 500:
        return ProviderFailure("server", "上游服务异常", True)
    return ProviderFailure("unknown", "未知错误", True)
~~~

收益：失败后可以按类型处理，不再全部“无脑重试”。

---

## Phase 2（2-3 天）：可用性优先与 token 可用性

### 6.1 模型可用性缓存（减少重复探测耗时）

新增 health store：记录 model 最后状态、失败原因、最近成功时间。

~~~python
# python_scripts/health_store.py
from __future__ import annotations
import json
import time
from pathlib import Path

HEALTH_PATH = Path("data/model-health.json")


def load_health() -> dict:
    if not HEALTH_PATH.exists():
        return {}
    return json.loads(HEALTH_PATH.read_text(encoding="utf-8"))


def save_health(data: dict) -> None:
    HEALTH_PATH.parent.mkdir(parents=True, exist_ok=True)
    HEALTH_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def upsert_health(provider: str, model: str, ok: bool, reason: str | None = None) -> None:
    state = load_health()
    key = f"{provider}/{model}"
    state[key] = {
        "ok": ok,
        "reason": reason,
        "checked_at": int(time.time()),
    }
    save_health(state)
~~~

建议 TTL：10 分钟。TTL 内优先使用上次成功模型。

### 6.2 预算友好的 token 策略（避免“能调但输出几乎不可用”）

按 provider 设定默认输入上限和压缩策略。

~~~python
# python_scripts/token_policy.py
from dataclasses import dataclass

@dataclass(frozen=True)
class TokenPolicy:
    max_input_chars: int
    reserve_output_tokens: int

DEFAULT_POLICY = {
    "github": TokenPolicy(max_input_chars=6000, reserve_output_tokens=256),
    "groq": TokenPolicy(max_input_chars=12000, reserve_output_tokens=384),
    "openrouter": TokenPolicy(max_input_chars=16000, reserve_output_tokens=512),
}


def trim_prompt(provider: str, text: str) -> str:
    policy = DEFAULT_POLICY.get(provider, TokenPolicy(max_input_chars=8000, reserve_output_tokens=256))
    if len(text) <= policy.max_input_chars:
        return text
    head = int(policy.max_input_chars * 0.7)
    tail = policy.max_input_chars - head
    return text[:head] + "\n\n...[内容已截断]...\n\n" + text[-tail:]
~~~

收益：在免费额度下提高首包成功率，避免一次请求直接超限。

### 6.3 快速选模算法（减少用户试错）

策略：

1. 先取最近 10 分钟成功模型。
2. 再取 provider 官方 hint 模型。
3. 失败按错误类型决定是否切 provider。

~~~python
# python_scripts/service.py（示意）
def choose_candidates(provider: str, requested_model: str | None, health: dict, hints: list[str]) -> list[str]:
    ordered: list[str] = []
    if requested_model:
        ordered.append(requested_model)

    healthy = [
        key.split("/", 1)[1]
        for key, value in health.items()
        if key.startswith(f"{provider}/") and value.get("ok")
    ]
    for m in healthy + hints:
        if m not in ordered:
            ordered.append(m)
    return ordered
~~~

---

## Phase 3（2 天）：小白前端配置闭环

目标：做一个“3 步完成”页面。

1. 配 key。
2. 一键验证。
3. 选择推荐模型并复制调用示例。

### 7.1 Python API 增补

建议新增：

- GET /api/provider-keys：返回各 provider 是否已配置（脱敏）。
- POST /api/provider-keys/{provider}：保存 key 到 .env。
- POST /api/provider-keys/{provider}/verify：验证 key。
- GET /api/providers/{provider}/models/recommended：返回按可用性排序的模型。

### 7.2 .env 写入逻辑（保留可维护性）

~~~python
# python_scripts/env_store.py
from pathlib import Path


def upsert_env(path: Path, key: str, value: str) -> None:
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    updated = False
    out: list[str] = []

    for line in lines:
        if line.strip().startswith(f"{key}="):
            out.append(f"{key}={value}")
            updated = True
        else:
            out.append(line)

    if not updated:
        out.append(f"{key}={value}")

    path.write_text("\n".join(out) + "\n", encoding="utf-8")
~~~

注意：前端只传明文一次，后端存储后返回脱敏版本。

### 7.3 前端核心逻辑（最少心智负担）

~~~javascript
// python_scripts/web/app.js（示意）
async function saveAndVerify(provider, apiKey) {
  await fetch(`/api/provider-keys/${provider}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ api_key: apiKey })
  });

  const verify = await fetch(`/api/provider-keys/${provider}/verify`, { method: 'POST' });
  const result = await verify.json();

  if (!result.ok) {
    showStatus(provider, `验证失败：${result.error}`, 'error');
    return;
  }

  showStatus(provider, '验证成功，正在获取推荐模型...', 'success');
  const modelsRes = await fetch(`/api/providers/${provider}/models/recommended`);
  const models = await modelsRes.json();
  renderRecommendedModels(provider, models.items || []);
}
~~~

收益：用户路径极短，降低“配置后不知道下一步做什么”的问题。

---

## 8. provider 扩展策略（借鉴两个参考仓库）

### 8.1 来源分层

1. 第一层：官方 API 文档可验证（高可信）。
2. 第二层：社区列表（高覆盖）。
3. 第三层：人工测试结果（高可用）。

### 8.2 数据结构建议

~~~json
{
  "provider": "openrouter",
  "kind": "free",
  "signup_required": true,
  "api_compatible": "openai",
  "models": [
    {
      "id": "openai/gpt-oss-20b:free",
      "context_window": 128000,
      "free_tier": true,
      "status": "active"
    }
  ],
  "limits": {
    "rpm": 20,
    "rpd": 50
  },
  "source": "official+community",
  "updated_at": "2026-03-25"
}
~~~

用途：后续可自动生成“推荐列表 + 说明文案 + 限制提示”。

---

## 9. 关键逻辑：避免“可用但用不起来”

### 9.1 请求前预检查

- 检查 provider key 是否配置。
- 检查请求体是否超过 provider 默认输入预算。
- 检查模型是否在最近失败冷却期内（如 3 分钟）。

### 9.2 失败回退规则

1. 同 provider 不同模型回退（最多 2 次）。
2. 再切换到次优 provider（最多 1 次）。
3. 返回明确错误与下一步建议，不返回模糊报错。

### 9.3 用户可见反馈标准

- 显示失败分类（鉴权失败、额度不足、频率限制、模型下线）。
- 显示建议动作（换 key、等重置、切模型、切 provider）。

---

## 10. 质量保障（最小但有效）

### 10.1 测试补充清单

1. URL 构造器测试：base/path/query 组合覆盖。
2. 错误分类测试：401/403/404/429/5xx。
3. token 策略测试：超长输入截断。
4. .env upsert 测试：新增/更新/保留注释。
5. 推荐模型排序测试：最近成功优先。

### 10.2 可观测性

在日志中增加字段：

- provider
- requested_model
- actual_model
- error_category
- latency_ms
- fallback_count

---

## 11. 执行排期（可直接开工）

Day 1:

1. 引入 provider_catalog.py 并改造 config.py 引用。
2. 引入 build_url 与错误分类。
3. 补齐对应单元测试。

Day 2:

1. 引入 health_store.py 与缓存 TTL。
2. 引入 token_policy.py。
3. 改造 service.probe 与 chat 回退。

Day 3:

1. 增加 provider key 管理 API。
2. 增加 .env upsert 逻辑。
3. 接入前端最小配置页（可先复用现有 public/index.html 结构）。

Day 4:

1. 优化模型推荐展示与错误提示。
2. 全链路回归测试。
3. 输出用户使用说明（含常见错误排查）。

---

## 12. 验收标准（Definition of Done）

1. 新增一个 provider 只需改 1 处元数据文件。
2. key 配置后 10 秒内给出可用性验证结果。
3. 对常见错误能输出明确分类与建议。
4. 同一个失败模型不会在短时间内被重复盲测。
5. 小白用户可在页面 3 步完成可用配置。
6. 项目代码阅读路径清晰（核心入口不超过 5 个文件）。

---

## 13. 与当前仓库对齐建议

考虑到仓库已存在 Node/TS 前端与 API 能力，推荐策略如下：

1. 短期：复用现有 public/index.html 交互设计，先把 Python 后端补齐 key 管理与推荐接口。
2. 中期：由 Python 统一承担“可用性与策略层”，Node 端仅保留兼容路由或逐步下线。
3. 长期：provider 目录、模型健康、限流策略统一为一份数据源，避免双实现漂移。

这样可以最大化复用你现有成果，同时保持“简单、可维护、易理解”的学习型项目定位。

---

## 14. Phase 1 执行 Todo（TDD 实施状态）

更新时间：2026-03-25

### 14.1 Red-Green 进度

- [x] Red：先写测试并运行，确认失败（`ImportError: cannot import name build_url`）。
- [x] Green：完成代码实现并修复失败点。
- [x] 回归：运行 `python3 -m unittest discover -s python_scripts/tests -p 'test_*.py'`。
- [x] 结果：11/11 测试通过。

### 14.2 Phase 1 完成项

- [x] Provider 目录化：新增 `python_scripts/provider_catalog.py`，集中维护 provider 元数据。
- [x] Config 改造：`python_scripts/config.py` 改为从 catalog 读取 provider/model hint/query。
- [x] 统一 URL 构造：在 `python_scripts/client.py` 新增 `build_url` 并统一拼接 URL。
- [x] 错误分类能力：新增 `python_scripts/errors.py`，提供 `classify_error`。
- [x] 测试补齐：在 `python_scripts/tests/test_config.py`、`python_scripts/tests/test_client.py` 增加 Phase 1 对应测试。

### 14.3 每个 Provider 可用性测试状态（基于当前 .env API Key）

测试方式：逐个执行 `python_scripts/smoke_*.py`。

| Provider | 状态 | 结果 | 说明 |
| --- | --- | --- | --- |
| openrouter | 已测试 | 失败 | `Insufficient credits`，账号 credits 不足 |
| groq | 已测试 | 失败 | `获取模型失败`（list models 阶段失败） |
| opencode | 已测试 | 失败 | `获取模型失败`（list models 阶段失败） |
| gemini | 已测试 | 失败 | `quota exceeded`（免费额度/速率额度为 0） |
| github | 已测试 | 成功 | probe 成功，`actual_model=openai/gpt-4o-mini` |
| mistral | 已测试 | 成功 | probe 成功，`actual_model=mistral-small-latest` |
| cerebras | 已测试 | 失败 | probe 失败，返回 `连通失败` |
| sambanova | 已测试 | 成功 | probe 成功，`actual_model=Meta-Llama-3.1-8B-Instruct` |

### 14.4 下一步待办（进入 Phase 2 前）

- [ ] 优先修复 `groq/opencode` 的模型列表接口兼容问题（`/models` 返回格式与鉴权信息排查）。
- [ ] 给 `openrouter/gemini` 增加额度不足的用户友好提示（前端可直接展示可操作建议）。
- [ ] 为 `cerebras` 增加更稳的 probe 候选模型与错误细分（auth/network/quota）。

---

## 15. Phase 2 执行 Todo（TDD 实施状态）

更新时间：2026-03-25

### 15.1 Red-Green 进度

- [x] Red：先新增 Phase 2 测试（health_store/token_policy/service fallback）。
- [x] Red 结果：出现 3 个预期失败（缺少 `health_store`、`token_policy`、`choose_candidates`）。
- [x] Green：完成模块实现和 service/server 集成。
- [x] 回归：运行 `python3 -m unittest discover -s python_scripts/tests -p 'test_*.py'`。
- [x] 结果：17/17 测试通过。

### 15.2 Phase 2 完成项

- [x] 新增 `python_scripts/health_store.py`：支持健康状态读写、upsert、可注入路径与时间（便于测试）。
- [x] 新增 `python_scripts/token_policy.py`：按 provider 默认预算做 prompt 截断。
- [x] `python_scripts/service.py` 新增 `choose_candidates`：按请求模型 > TTL 内健康模型 > hints 排序。
- [x] `python_scripts/service.py` 新增 `chat()`：接入 prompt 截断、候选回退、健康状态写入。
- [x] `python_scripts/service.py` 的 `probe()` 复用 `chat(..., 'ok')`，避免逻辑重复。
- [x] `python_scripts/server.py` 的 `/chat/completions` 改为调用 `service.chat()`。

### 15.3 Phase 2 测试覆盖

- [x] `python_scripts/tests/test_health_store.py`
    - 缺失文件返回空字典
    - upsert 后状态持久化
- [x] `python_scripts/tests/test_token_policy.py`
    - 短文本不截断
    - 长文本截断并保留头尾
- [x] `python_scripts/tests/test_service.py`
    - 候选排序优先级（requested > healthy > hints）
    - chat 回退链路（首模型失败后回退成功）
    - prompt 截断逻辑确实生效

---

## 16. Phase 3 执行 Todo（TDD 实施状态）

更新时间：2026-03-25

### 16.1 Red-Green 进度

- [x] Red：先新增 Phase 3 测试（`.env` 写入、key 状态/保存/验证、推荐模型）。
- [x] Red 结果：出现 3 个预期失败（缺少 `env_store`、`ProxyService` 缺少 `dotenv_path` 与 Phase 3 方法）。
- [x] Green：补齐 `env_store`、`service`、`server` 与前端页面。
- [x] 回归：运行 `python3 -m unittest discover -s python_scripts/tests -p 'test_*.py'`。
- [x] 结果：21/21 测试通过。

### 16.2 Phase 3 完成项

- [x] 新增 `python_scripts/env_store.py`
    - 支持 `.env` 键值新增与覆盖更新。
    - 保留注释和非键值行。
- [x] 扩展 `python_scripts/service.py`
    - 支持 `dotenv_path` 注入，便于测试和多环境使用。
    - 新增 `provider_key_statuses()`（基于 `.env` 文件状态）。
    - 新增 `save_provider_key()`（保存到 `.env` 并更新当前进程环境）。
    - 新增 `verify_provider_key()`（验证 key 并返回模型列表）。
    - 新增 `recommended_models()`（结合健康状态与模型列表给出推荐序列）。
- [x] 扩展 `python_scripts/server.py`
    - 新增 `GET /api/provider-keys`
    - 新增 `POST /api/provider-keys/{provider}`
    - 新增 `POST /api/provider-keys/{provider}/verify`
    - 新增 `GET /api/providers/{provider}/models/recommended`
    - 新增 Python 内置静态页面入口：`/`、`/ui`。
- [x] 新增小白可用配置页面 `python_scripts/web/index.html`
    - 配置 key
    - 验证 key
    - 查看推荐模型

### 16.3 Phase 3 测试覆盖

- [x] `python_scripts/tests/test_env_store.py`
    - 缺失键追加
    - 已有键覆盖并保留注释
- [x] `python_scripts/tests/test_service.py`
    - key 状态读取与保存
    - key 验证
    - 推荐模型接口行为

---

## 17. 集成修复记录（Groq + 错误分类 + 复测）

更新时间：2026-03-25

### 17.1 已完成修复

- [x] Groq `/models` 兼容回退
    - 在 provider catalog 中补充 Groq 模型 hints。
    - 当 Groq `/models` 返回 4xx 或非标准数据时，回退到 hints，避免 `verify_key` 直接失败。
- [x] `verify_key` 错误分类
    - 引入 `ProviderHTTPError(status, category)`。
    - `verify_provider_key` 返回 `category` 字段（如 `auth`、`rate_limit`、`quota`）。
    - 在 `models` 受限时增加“用 hint 模型做轻量连通探测”的后备路径。
- [x] 测试覆盖与回归
    - 新增 Groq fallback 测试。
    - 新增 verify 错误分类测试。
    - 全量测试：`23/23` 通过。

### 17.2 端到端复测（使用用户提供新 key）

测试链路：保存 key -> 验证 key -> 推荐模型 -> probe -> chat。

| Provider | save_key | verify_key | recommended | probe | chat | 结论 |
| --- | --- | --- | --- | --- | --- | --- |
| groq | 成功 | 成功（2 个模型） | 成功（2 个） | 失败（连通失败） | 失败（连通失败） | key 可保存+可验证，但推理链路未跑通 |
| sambanova | 成功 | 成功（16 个模型） | 成功（16 个） | 成功 | 成功 | 全链路跑通 |

### 17.3 当前判断

- Groq 当前问题从“无法验证”收敛为“可验证但推理失败”。
- SambaNova 新 key 已确认可稳定跑通当前项目全链路。

---

## 18. 统一可用性增强（全 Provider 覆盖）

更新时间：2026-03-25

### 18.1 目标

把 Groq 暴露的问题抽象成全 provider 通用能力，避免“每家单独打补丁”。

### 18.2 已落地能力

- [x] 统一错误分类增强（支持无状态码文本识别）
    - 支持识别：`auth`、`quota`、`rate_limit`、`model_not_found`、`network`、`server`。
- [x] 统一可执行建议生成（`remediation_suggestion`）
    - 每个错误类别都有可直接执行的处理建议。
- [x] `verify_key` 升级为“可调用验证优先”
    - 不再只依赖 `/models`。
    - `models` 可列出也必须至少有一个候选模型真实可调用才判定 `ok=true`。
- [x] 全 provider 默认 hints 覆盖
    - openrouter/opencode/gemini/groq/github/mistral/cerebras/sambanova 全部有基础候选模型。
- [x] 统一返回诊断字段
    - `category`、`status`、`suggestion`。

### 18.3 测试结果

- 全量测试：`26/26` 通过。

### 18.4 修复后端到端复测（用户提供 key）

| Provider | verify_key | probe | chat | 关键诊断 |
| --- | --- | --- | --- | --- |
| groq | 失败 | 失败 | 失败 | `category=auth`, `status=403`, suggestion 已返回（疑似 key 权限/账号侧限制） |
| sambanova | 成功 | 成功 | 成功 | 全链路正常 |

### 18.5 当前收益

- 即使不是“额度问题”，系统也能区分“权限、限流、模型错误、网络、上游异常”等原因。
- 同一套诊断与建议机制已覆盖所有 provider，不再是单 provider 特判。

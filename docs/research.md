# free-proxy 当前主线结构说明（2026-03-30）

## 1. 结论

- 当前唯一运行主线：`python_scripts/`
- 历史 TypeScript 方案不再参与运行与决策
- 若需追溯旧设计，只看 `docs/typescript-legacy.md`

## 2. 对外稳定面

- OpenAI 兼容接口：
  - `GET /v1/models`
  - `POST /v1/chat/completions`
- 稳定别名：
  - `free-proxy/auto`
  - `free-proxy/coding`
- Python 服务端兼容输入：
  - `auto` / `coding`
  - `free-proxy/auto` / `free-proxy/coding`
  - `free_proxy/auto` / `free_proxy/coding`

## 3. 当前模块分层

### 3.1 Provider Catalog

- 文件：`python_scripts/provider_catalog.py`
- 职责：provider 名称、base URL、API key 环境变量、协议格式、模型 hints、required query
- 约束：这里只存事实，不存 fallback 策略

### 3.2 Provider Routing

- 文件：`python_scripts/provider_routing.py`
- 职责：
  - 解析 `auto` / `coding` / `free-proxy/...` / `provider/model`
  - 产出 alias 候选顺序
  - 基于健康状态重排候选模型

### 3.3 Provider Adapter / Transport

- 文件：
  - `python_scripts/provider_errors.py`
  - `python_scripts/provider_transport.py`
  - `python_scripts/provider_adapter.py`
- 职责：
  - 统一 HTTP 传输
  - 处理 OpenAI / Gemini 协议差异
  - 保留 Longcat 超时、OpenRouter 免费模型过滤、Gemini 文本模型过滤、GitHub/Groq/Longcat/Nvidia hints fallback

### 3.4 Service

- 文件：`python_scripts/service.py`
- 职责：
  - provider key 状态
  - verify / probe / chat
  - token budget 学习与重试
  - alias/direct OpenAI forward orchestration

### 3.5 HTTP Server

- 文件：`python_scripts/server.py`
- 职责：
  - 路由
  - 请求解析
  - OpenAI 兼容响应转换
  - 统一错误返回

## 4. 当前路由规则

- `free-proxy/auto` / `auto`：按公开 alias 顺序路由
- `free-proxy/coding` / `coding`：按 coding alias 顺序路由
- `provider/model`：直连指定 provider
- 仅写模型名且未显式给 provider：默认使用第一个已配置 provider

## 5. 当前验证链路

- provider key 保存后，通过 `verify_provider_key()` 先拉模型列表，再做真实 probe
- probe 使用小输出预算，真实 chat 使用常规输出预算
- token limit 错误会写入 `data/token-limits.json` 并自动重试一次
- 健康状态会写入 `data/model-health.json`

## 6. 验收命令

```bash
uv run python -m unittest discover -s python_scripts/tests -p 'test_*.py'
npm test -- --runInBand
npx tsc --noEmit
```

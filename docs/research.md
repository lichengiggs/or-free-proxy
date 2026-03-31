# free-proxy 当前主线结构说明（2026-03-30）

## 1. 结论

- 当前唯一运行主线：`python_scripts/`
- 历史 TypeScript 方案已清理，不再单独保留档案
- 当前长期技术总览只有这一份文档
- 文档路径：`docs/research.md`

## 2. 对外稳定面

- OpenAI 兼容接口：
  - `GET /v1/models`
  - `POST /v1/chat/completions`
- 稳定别名：
  - `free-proxy/auto`
- Python 服务端兼容输入：
  - `auto`
  - `free-proxy/auto`
  - `free_proxy/auto`

## 3. 当前模块分层

### 3.1 Provider Catalog

- 文件：`python_scripts/provider_catalog.py`
- 职责：provider 名称、base URL、API key 环境变量、协议格式、模型 hints、required query
- 约束：这里只存事实，不存 fallback 策略

### 3.2 Provider Routing

- 文件：`python_scripts/provider_routing.py`
- 职责：
  - 解析 `auto` / `free-proxy/...`
  - 产出 `auto` 候选顺序
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
  - verify / probe
  - relay accessor
  - token budget 学习与重试
  - provider 侧推荐模型与本地状态维护

### 3.5 OpenAI Relay

- 文件：
  - `python_scripts/request_normalizer.py`
  - `python_scripts/fallback_policy.py`
  - `python_scripts/protocol_converter.py`
  - `python_scripts/response_normalizer.py`
  - `python_scripts/openai_relay.py`
- 职责：
  - 校验公开模型面，只接受 `auto`
  - 统一提取 `requested_model`、`messages`、输出预算
  - 构建 health + hints + 静态 fallback 候选池
  - 按错误分类执行 fallback
  - 把上游 JSON / SSE 统一收敛为 OpenAI JSON / SSE

### 3.6 HTTP Server

- 文件：`python_scripts/server.py`
- 职责：
  - 路由
  - 请求解析
  - 统一错误返回
  - relay 结果写回

## 4. 当前路由规则

- `free-proxy/auto` / `auto`：按健康驱动候选池路由
- `coding` / `free-proxy/coding` / `free_proxy/coding`：拒绝并返回 `model_deprecated`
- `requested_model` 只作为内部路由偏好，不属于公开稳定接口

## 5. 当前验证链路

- provider key 保存后，通过 `verify_provider_key()` 先拉模型列表，再做真实 probe
- probe 使用小输出预算，真实 chat 使用常规输出预算
- token limit 错误会写入本地 `data/token-limits.json` 并自动重试一次
- 健康状态会写入本地 `data/model-health.json`
- 这两个文件是运行时状态，不入库
- provider `/models` 不稳定时，路由仍需保留 `model_hints` 兜底
- provider 动态列出的候选模型会在当前 provider 静态默认模型失败后再懒加载，不等所有 provider 都失败

## 6. 验收命令

```bash
uv run python -m unittest discover -s python_scripts/tests -p 'test_*.py'
npm test -- --runInBand
npx tsc --noEmit
```

## 7. Debug 排障模式

- 启动命令：`uv run free-proxy serve --debug`
- 作用：把请求、路由、上游状态和错误分类打印到终端
- 约束：不打印 API key、prompt 原文、message 内容、完整响应体
- 适用场景：远程用户无法稳定复现，只能贴终端日志

## 8. 本地流式验收注意事项

- 验证 `127.0.0.1` 流式链路前，先检查 shell 里的 `http_proxy` / `https_proxy`
- 如存在代理，必须设置 `NO_PROXY=127.0.0.1,localhost` 或临时清空代理变量
- 否则代理可能注入 `Connection: keep-alive` / `Proxy-Connection: keep-alive`，把已正常结束的 SSE 误判成服务端未关闭连接

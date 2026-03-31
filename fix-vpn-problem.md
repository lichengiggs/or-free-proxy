# free-proxy / opencode 兼容问题研究

## 状态

- 已完成：确认 VPN / 代理不是唯一根因。
- 已完成：确认 provider 本身并未整体失效，`longcat`、`gemini`、`github` 直连 probe 可成功。
- 已完成：确认当前问题不只是 opencode 客户端问题，现有 `8765` 服务上的 `/v1/chat/completions` 也可能直接返回 `502 all candidates failed`。
- 已完成：决定不再继续维护“上游 provider 的”OpenAI 兼容流式主链路。
- 已完成：`/v1/chat/completions` 默认收敛为非流式 JSON；仅在客户端显式 `stream=true` 时做最小 SSE 包装兼容。
- 已完成：确认 Web UI 把 JSON 当正文显示的根因是前端仍按流式 fallback 读取 `/chat/completions`。
- 已完成：确认 opencode 收到响应但正文为空的根因是 `/v1/chat/completions` 归一化时只提取了 `message.content` 字符串，漏掉 `reasoning_content` 与数组内容。
- 已完成：确认 Longcat thinking 仍使用固定 timeout，长任务更容易超时。
- 已完成：`uv run python -m unittest discover -s python_scripts/tests -p 'test_*.py'` 通过。
- 已完成：`npm test` 通过。
- 已完成：`npx tsc --noEmit` 通过。
- 已完成：`opencode run` 在清空本地代理变量后可正常输出正文。

## 现象

- Web UI 中 Longcat 模型可用。
- opencode 中使用 `free-proxy/auto` 失败，表现为 `all candidates failed`。
- 本机存在代理环境变量，但去掉代理后问题依然存在。

## 最新证据

1. 直接 provider probe 成功：
   - `uv run python -m python_scripts.cli probe --provider longcat --model LongCat-Flash-Lite` 成功
   - `uv run python -m python_scripts.cli probe --provider gemini --model gemini-3.1-flash-lite-preview` 成功
   - `uv run python -m python_scripts.cli probe --provider github --model gpt-4o` 成功
2. 这说明上游 provider key 不是整体失效，主问题在 relay 主链路或正在运行的服务实例。
3. 之前把问题集中在 SSE/stream 兼容上，只解释了部分现象，但没有真正降低系统复杂度。
4. `/chat/completions` 在 `stream=true` 且上游实际返回 JSON 时，前端 `requestStream(...)` 直接 `response.text()`，所以 UI 会展示整段 JSON。
5. `/v1/chat/completions` 的 relay 归一化逻辑只读取 `choices[0].message.content` 字符串，导致 reasoning-only 响应会被归一化成空正文。
6. `longcat` thinking 模型能力表仍写死 `default_timeout_seconds=30`，请求 timeout 没有区分长任务预算。
7. 新增关键证据：`opencode` 的 OpenAI 兼容调用在 `stream=true` 时会按 SSE 消费；如果 `/v1/chat/completions` 返回普通 JSON，`opencode run` 会出现 `tokens.output=0` 或卡住不退出。
8. 新增关键证据：本机 shell 设置了 `http_proxy` / `https_proxy`，会影响 `127.0.0.1` 流式链路；清空代理变量并设置 `NO_PROXY=127.0.0.1,localhost` 后，`opencode run` 能正常输出 `验证通过` 并退出。

## 根因判断

这次问题暴露出的核心不是某一个流式 bug，而是整体设计复杂度过高：

1. 同一个 OpenAI 兼容入口同时维护非流式 JSON 和流式 SSE 两套主链路。
2. `stream=true` 会把问题面放大到：
   - SSE 事件格式
   - chunk 归一化
   - `[DONE]` 结束语义
   - 本地代理/连接行为
   - 不同客户端的流式实现差异
3. 对 coding agent 来说，这类复杂度并没有带来足够收益，反而持续制造排查成本。

因此，本次不再继续修补“上游 provider 的流式主链路”，而是统一先拿完整 JSON，再按客户端需要决定输出形态：默认 JSON；`stream=true` 时再做最小 SSE 包装。遗留的旧 `/chat/completions` 页面链路则继续保留最小兼容修复。

## 最终方案

### 方案选择

- 采用方案：上游 provider 统一改成非流式。
- 兼容策略：
  - 默认返回普通 JSON；
  - 客户端若显式传 `stream=true`，服务端把已拿到的完整 JSON 结果包装成最小 SSE 返回给客户端。

### 具体调整

1. `python_scripts/openai_relay.py` 对上游 provider 一律传 `stream=False`，统一走完整 JSON body。
2. `POST /v1/chat/completions` 在 `stream=false` 下返回标准 OpenAI JSON。
3. `POST /v1/chat/completions` 在 `stream=true` 下，把完整 JSON body 包装成最小 `chat.completion.chunk` SSE，并以 `[DONE]` 收尾。
4. `python_scripts/service.py` 对 OpenAI provider 统一走 `chat_completions_raw(...)`，不再走 `chat_completions_stream(...)` 上游主链路。
5. `python_scripts/response_normalizer.py` 负责 JSON 成功归一化，以及 JSON->SSE 的最小包装。
6. README 与验证文档统一说明：本地验证 `127.0.0.1` 流式链路时，必须设置 `NO_PROXY=127.0.0.1,localhost` 或临时清空代理变量。
7. Web UI 在非 SSE fallback 时，必须从 JSON 中提取真实正文，而不是显示整段 JSON。
8. OpenAI relay 归一化时，必须同时兼容 `message.content`、`message.reasoning_content`、数组 `content[]` 和 `choice.text`。
9. Longcat thinking 作为 `long_running` 模型，timeout 至少放宽到基础能力值的 2 倍，避免 30 秒固定超时过早中断长回复。

## 为什么这样做

1. coding agent 追求的是稳定和兼容，不是逐 token 输出。
2. 删除“上游 SSE 主链路”后，问题边界只剩：
    - 候选模型选择
    - 上游 provider 请求
    - 普通 JSON 错误映射
    - 客户端侧最小 SSE 包装
3. 这比继续维护两套独立的上游协议行为更简单，也更容易排查和维护。

## 已完成任务

- [x] 排除 VPN / 代理是唯一根因
- [x] 确认 `free-proxy/auto` 候选池顺序
- [x] 确认 provider 直连 probe 可成功
- [x] 决定移除上游 provider 的流式主链路
- [x] 将 `/v1/chat/completions` 统一收敛为“默认 JSON + `stream=true` 最小 SSE 包装”
- [x] 更新 OpenAI relay / service / response normalizer 定向测试
- [x] 修复 Web UI 在 JSON fallback 下把整段响应当正文显示
- [x] 修复 OpenAI relay 漏提取 `reasoning_content` 导致正文为空
- [x] 放宽 Longcat thinking 长任务 timeout
- [x] 确认 `opencode run` 需要 SSE 消费 `stream=true` 请求
- [x] 确认清空代理变量后 `opencode run` 可正常输出正文

## 验收标准

1. `/v1/chat/completions` 在 `stream=false` 下返回 JSON。
2. `/v1/chat/completions` 在 `stream=true` 下返回最小 SSE chunk，并以 `data: [DONE]` 正常结束。
3. Web UI 在 `/chat/completions` 返回 JSON 时显示真实正文而非整段 JSON。
4. opencode 非交互调用 `free-proxy/auto` 时，在清空本地代理变量后能正常输出正文。
5. Longcat thinking 长回复不再被固定 30 秒 timeout 过早截断。

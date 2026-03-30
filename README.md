# free-proxy

[中文](README.md) | [English](README_EN.md)

把多家免费 LLM provider 聚合成一个本地 OpenAI 兼容入口。你只需要配好 API Key，就能先跑起来，再按需要切模型。

适合这三类人：
- 想低成本体验多家免费模型的人
- 想给 OpenAI SDK / OpenClaw / Opencode 提供统一本地入口的人
- 不想手动维护多套 provider 配置的人

## 你能得到什么

- 一个本地 OpenAI 兼容地址：`http://127.0.0.1:8765/v1`
- 两个稳定模型别名：`free-proxy/auto`、`free-proxy/coding`
- 多 provider 自动回退，某家失败时可切到其他可用模型
- 本地 Web 页面配置 API Key，不用手改复杂配置

## 当前主推荐

如果你只想先用起来，优先配 Longcat：

| Provider | 推荐模型 | 适合场景 | 说明 |
|---|---|---|---|
| Longcat | `LongCat-Flash-Lite` | 默认首选 | 当前最省心，免费额度大 |
| Gemini | `gemini-3.1-flash-lite-preview` | Longcat 备用 | 免费层稳定，适合回退 |
| Mistral | `mistral-large-latest` | 稳定后备 | 质量稳，适合补位 |
| GitHub Models | `gpt-4o` / `gpt-4o-mini` | 已有 Copilot 的用户 | 质量高，但额度取决于账号 |
| SambaNova | `DeepSeek-V3.1-Terminus` | 补充选择 | 适合作为额外后备 |

## 3 步快速开始

### 1) 克隆项目

```bash
git clone https://github.com/lichengiggs/free-proxy.git
cd free-proxy
```

### 2) 安装依赖

先安装 [uv](https://docs.astral.sh/uv/)。

macOS / Linux：

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

或 Homebrew：

```bash
brew install uv
```

然后在项目根目录执行：

```bash
uv sync
```

### 3) 启动并配置

启动服务：

```bash
uv run free-proxy serve
```

打开浏览器：

```text
http://127.0.0.1:8765
```

然后按这个顺序操作：
1. 保存至少一个 provider 的 API Key
2. 先选推荐模型
3. 点验证，或直接发一条测试消息

小白提示：服务启动后，这个终端窗口先不要关。

## 成功后怎么用

### OpenAI SDK / Python

- Base URL：`http://127.0.0.1:8765/v1`
- 默认模型：`free-proxy/auto`
- 代码任务：`free-proxy/coding`

```python
from openai import OpenAI

client = OpenAI(
    api_key="not-needed",
    base_url="http://127.0.0.1:8765/v1",
)

resp = client.chat.completions.create(
    model="free-proxy/auto",
    messages=[{"role": "user", "content": "Reply with exactly OK"}],
)

print(resp.choices[0].message.content)
```

### OpenClaw

- Provider：`free-proxy`
- Base URL：`http://127.0.0.1:8765/v1`
- 可用模型：`auto`、`coding`
- 不确定时先用：`free-proxy/auto`
- 主要写代码时用：`free-proxy/coding`

### Opencode

- Provider：`free-proxy`
- Base URL：`http://127.0.0.1:8765/v1`

默认测试命令：

```bash
opencode run -m free-proxy/auto "Reply with exactly OK"
```

代码任务命令：

```bash
opencode run -m free-proxy/coding "Reply with exactly OK"
```

## 对外稳定接口

当前对外兼容面固定为：
- `GET /v1/models`
- `POST /v1/chat/completions`
- `free-proxy/auto`
- `free-proxy/coding`

如果你只记一条：
- 平时先用 `free-proxy/auto`
- 主要写代码时换成 `free-proxy/coding`

## 常见问题

### `uv sync` 报 `No pyproject.toml found`
说明你不在仓库根目录。

先执行：

```bash
cd free-proxy
ls pyproject.toml
```

如果能看到 `pyproject.toml`，再执行：

```bash
uv sync
```

### 页面打不开 / 请求失败
先确认服务还在运行：

```bash
uv run free-proxy serve
```

然后访问：

```text
http://127.0.0.1:8765
```

### 更新后启动失败
按这个顺序执行：

```bash
git pull --ff-only
uv sync
uv run free-proxy serve
```

### 没有可用模型
免费模型可能临时限流。先刷新模型列表，再换一个推荐模型重试。

### API Key 存在哪里
保存在项目根目录的本地 `.env` 文件，不会提交到 GitHub。

### 旧配置里看到 `free_proxy`
这是旧命名。现在统一使用 `free-proxy`。

## 开发命令

启动服务：

```bash
uv run free-proxy serve
```

查看命令：

```bash
uv run free-proxy --help
```

运行 Python 测试：

```bash
uv run python -m unittest discover -s python_scripts/tests -p 'test_*.py'
```

运行前端 / 历史静态测试：

```bash
npm test
```

## 历史说明

- TypeScript 后端已归档并退出运行路径；当前唯一运行入口是 Python。
- 长期技术总览：`docs/research.md`

## License

MIT

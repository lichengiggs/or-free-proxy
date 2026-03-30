# free-proxy

[中文](README.md) | [English](README_EN.md)

聚合多家 provider 的免费层，变成一个可用的 token 池，方便个人开发与日常编码。

一句话概览：免费、易用、能足够日常OpenClaw使用。

### 免费额度一览

感谢 [free-llm-api-resources](https://github.com/cheahjs/free-llm-api-resources/tree/main?tab=readme-ov-file) 项目整理各家免费供应商信息。下表优先列出当前项目里最值得先配、最容易跑起来的入口；精确数字最终以各家官方页面为准。

| Provider | 推荐模型 | 免费额度 / 限制 | 备注 |
|---|---|---|---|
| Longcat | `LongCat-Flash-Lite` | 50,000,000 tokens/day | 当前主推荐，量最大 |
| Gemini | `gemini-3.1-flash-lite-preview` | 250,000 tokens/minute<br>500 requests/day<br>15 requests/minute | 已过滤 image / vision / embedding 模型 |
| Mistral | `mistral-large-latest` | 1 request/second<br>500,000 tokens/minute<br>1,000,000,000 tokens/month | 免费层很强，适合做稳定后备 |
| Groq | `llama-3.1-8b-instant` | 14,400 requests/day<br>6,000 tokens/minute | 响应快，适合轻量回退 |
| NVIDIA NIM | `meta/llama-3.1-70b-instruct` | 40 requests/minute | 新增高质量后备，模型多 |
| GitHub Models | `gpt-4o` / `gpt-4o-mini` | 取决于 Copilot tier（Free / Pro / Pro+ / Business / Enterprise） | 输入输出限制严格，但模型质量高 |
| SambaNova | `DeepSeek-V3-0324` | `$5 / 3 months` credits | 这里按 trial credit 看待，适合作为补充 |

## 核心功能

- 聚合 8 家高质量 provider（OpenRouter / Groq / Longcat / Gemini / GitHub Models / Mistral / SambaNova / NVIDIA NIM）
- 自动回退：当前模型失败或限流时自动切换到可用模型
- token limit 学习：遇到上下文超限后自动缩减一次，并把学习结果写入 `data/token-limits.json`
- 手动添加模型：支持 `provider+modelId` 直接添加
- 本地 Web 配置：卡片式保存 API Key，直接选模型并更新 OpenClaw
- OpenAI 兼容接口：`http://localhost:8765/v1`

## 快速开始

1) 首次安装：克隆仓库

```bash
git clone https://github.com/lichengiggs/free-proxy.git
cd free-proxy
```

如果你之前已经拉过这个仓库，后续更新用下面两条就够了：

```bash
cd free-proxy
git pull --ff-only
```

2) 安装 [uv](https://docs.astral.sh/uv/)（如果还没有）

macOS / Linux：

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Homebrew：

```bash
brew install uv
```

3) 回到仓库根目录

下面这一步必须在 `free-proxy` 仓库根目录执行，也就是当前目录里能看到 `pyproject.toml`。

```bash
cd free-proxy
```

如果你不确定自己现在是不是在对的目录，先执行：

```bash
pwd
ls pyproject.toml
```

如果第二条命令提示找不到文件，说明你当前不在仓库根目录。先切回 `free-proxy` 目录，再继续。

4) 初始化依赖

```bash
uv sync
```

如果这里出现 `No pyproject.toml found in current directory or any parent directory`，不是项目坏了，而是你不在仓库根目录。

如果你是更新老版本，进入仓库后重新执行一次 `uv sync`，把新依赖和脚本同步到本地。

5) 启动服务

```bash
uv run free-proxy serve
```

小白提示：启动后请保持这个窗口打开，不要关闭。

6) 打开配置页面并保存至少一个 provider 的 API Key

- 访问：`http://localhost:8765`
- 保存 Key 后，优先选推荐模型，再点一次验证或直接发一条测试请求。

## 常用接入方式

- OpenAI 兼容客户端 / Python SDK
  - Base URL：`http://127.0.0.1:8765/v1`
  - Model：`free-proxy/auto`（最省心，适合绝大多数情况）
  - 如果你主要拿它写代码，再换成 `free-proxy/coding`
  - 最小示例：

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

- OpenClaw
  - Provider：`free-proxy`
  - Base URL：`http://localhost:8765/v1`
  - 模型：`auto`、`coding`
  - 默认先用：`free-proxy/auto`
  - 如果主要做代码任务，再切到：`free-proxy/coding`

- Opencode
  - Provider：`free-proxy`
  - 如果要写配置文件，路径通常是：`~/.config/opencode/opencode.json`
  - Base URL：`http://localhost:8765/v1`
  - 默认命令：`opencode run -m free-proxy/auto "Reply with exactly OK"`
  - 代码任务命令：`opencode run -m free-proxy/coding "Reply with exactly OK"`

## 当前对外行为（与实现一致）

- 标准 OpenAI 兼容接口：
  - `GET /v1/models`
  - `POST /v1/chat/completions`
- 对外稳定模型别名：
  - `free-proxy/auto`
  - `free-proxy/coding`
- OpenClaw 配置写入：
  - provider id：`free-proxy`
  - models：`auto`、`coding`
- Opencode 配置写入：
  - provider id：`free-proxy`
  - models：`auto`、`coding`

小白直接记住一条就够了：

1. 不确定用什么模型时，先用：`free-proxy/auto`

如果你主要拿它写代码，再换成：`free-proxy/coding`

## 常见问题

- 网络错误：先确认服务还在运行（`uv run free-proxy serve`），再访问 `http://localhost:8765`
- 如果你开了全局 VPN / 系统代理：free-proxy 默认会跟随系统代理走。通常不会直接失效，但可能引发证书、地域限制或超时问题；遇到 `network` 类错误优先检查 VPN、代理和证书链
- 更新后启动失败：先执行 `git pull --ff-only`，再执行 `uv sync`
- `uv sync` 提示找不到 `pyproject.toml`：说明你不在仓库根目录，先执行 `cd free-proxy`，再用 `ls pyproject.toml` 确认当前目录正确
- 从 GitHub 一键复制命令后在 zsh 报错：只复制代码块里的命令，不要把代码块外的解释文字一起复制
- 无可用模型：免费模型可能被临时限流，先点“刷新模型列表”，再换一个推荐模型重试
- API Key 存放：本地 `.env`（不会上传）
- token 超限：系统会先用较大的默认预算（65,536 input / 4,096 output），若上游明确报超限，会自动缩减一次并把结果记到 `data/token-limits.json`
- 旧版 Opencode 配置里如果出现 `free_proxy`
  - 这是旧命名
  - 当前统一名称是 `free-proxy`
  - 重新执行一次配置写入后应统一为 `free-proxy`

## 开发命令

启动服务：

```bash
uv run free-proxy serve
```

查看所有子命令：

```bash
uv run free-proxy --help
```

列出某 provider 的模型：

```bash
uv run free-proxy models --provider sambanova
```

探测某模型可用性：

```bash
uv run free-proxy probe --provider sambanova --model DeepSeek-V3-0324
```

运行测试：

```bash
uv run python -m unittest discover -s python_scripts/tests -p 'test_*.py'
```

前端 / 历史静态测试（首次执行前先 `npm install`）：

```bash
npm test
```

## 历史方案

- TypeScript 历史方案已退出运行路径，仅保留文档归档；当前唯一运行入口是 Python。
- 历史说明见：`docs/typescript-legacy.md`
- 迁移发布说明见：`docs/migration-python-mainline.md`

## 许可

MIT

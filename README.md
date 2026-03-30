# free-proxy

中文 | English

把多家免费 LLM provider 聚合成一个本地 OpenAI 兼容入口。你只需要配好 API Key，就能先跑起来，再按需要切模型。

这份项目最适合这三类人：

1. 想低成本体验多家免费模型的人
2. 想给 OpenAI SDK / OpenClaw / Opencode 提供统一本地入口的人
3. 不想手动维护多套 provider 配置的人

## 你会得到什么

- 一个本地 OpenAI 兼容地址：`http://127.0.0.1:8765/v1`
- 两个稳定模型别名：`free-proxy/auto`、`free-proxy/coding`
- 多 provider 自动回退，某家失败时可切到其他可用模型
- 本地 Web 页面配置 API Key，不用手改复杂配置

## 安装 free-proxy

先把项目下载到本地：

```bash
git clone https://github.com/lichengiggs/free-proxy.git
cd free-proxy
```

然后启动服务：

```bash
uv run free-proxy serve
```

打开页面：

```text
http://127.0.0.1:8765
```

## 升级 free-proxy

如果你已经装过这个项目，在项目目录里执行：

```bash
git pull --ff-only
uv sync
uv run free-proxy serve
```

## 3 步快速开始

1. 保存至少一个 provider 的 API Key
2. 先选推荐模型
3. 点击验证，或者直接发一句测试消息

小白提示：服务启动后，这个终端窗口先不要关。

## 推荐怎么选

如果你只想先用起来，优先配 Longcat。

| Provider | 推荐模型 | 适合场景 | 说明 |
|---|---|---|---|
| Longcat | `LongCat-Flash-Lite` | 默认首选 | 当前最省心，免费额度大 |
| Gemini | `gemini-3.1-flash-lite-preview` | Longcat 备用 | 免费层稳定，适合回退 |
| Mistral | `mistral-large-latest` | 稳定后备 | 质量稳，适合补位 |
| GitHub Models | `gpt-4o` / `gpt-4o-mini` | 已有 Copilot 的用户 | 质量高，但额度取决于账号 |
| SambaNova | `DeepSeek-V3.1-Terminus` | 补充选择 | 适合作为额外后备 |

如果你只记一条：

- 不确定时先用 `free-proxy/auto`
- 主要写代码时换成 `free-proxy/coding`

## 排障日志

如果你想看更详细的排障日志，启动时加：

```bash
uv run free-proxy serve --debug
```

## 常见问题

### 页面打不开

先确认服务还在运行，再刷新页面。

### 没有可用模型

先换一个推荐模型再试。

### API Key 存在哪里

保存在项目根目录的 `.env` 文件里，不会提交到 GitHub。

## 致敬

这个项目参考并兼容了很多现成工作流，尽量把复杂度藏在后面，让小白能先用起来。

## License

MIT

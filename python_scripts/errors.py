from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderFailure:
    category: str
    message: str
    retryable: bool


def classify_error(status: int, body_text: str) -> ProviderFailure:
    text = (body_text or '').lower()
    if any(token in text for token in ('invalid api key', 'unauthorized', 'forbidden', 'permission denied')):
        return ProviderFailure('auth', 'API Key 无效或权限不足', False)
    if any(token in text for token in ('model not found', 'unknown model', 'unsupported model', 'does not exist')):
        return ProviderFailure('model_not_found', '模型不存在或路径错误', False)
    if any(token in text for token in ('quota exceeded', 'insufficient credits', 'billing', 'exceeded your current quota')):
        return ProviderFailure('quota', '额度不足', False)
    if any(token in text for token in ('rate limit', 'too many requests', 'retry later')):
        return ProviderFailure('rate_limit', '触发频率限制', True)
    if any(token in text for token in ('network', 'connection', 'timed out', 'timeout', 'certificate verify failed', 'local issuer certificate', 'ssl', 'tls')):
        return ProviderFailure('network', '网络连接失败', True)

    if status in (401, 403):
        return ProviderFailure('auth', 'API Key 无效或权限不足', False)
    if status == 404:
        return ProviderFailure('model_not_found', '模型不存在或路径错误', False)
    if status == 429:
        return ProviderFailure('rate_limit', '触发频率限制', True)
    if status == 402 or 'insufficient' in text or 'quota' in text:
        return ProviderFailure('quota', '额度不足', False)
    if status >= 500:
        return ProviderFailure('server', '上游服务异常', True)
    return ProviderFailure('unknown', '未知错误', True)


def remediation_suggestion(category: str, provider: str) -> str:
    if category == 'auth':
        return f'{provider} API Key 可能无效、过期或权限不足，请重新生成并确认已开通对应模型权限。'
    if category == 'quota':
        return f'{provider} 额度可能不足，请检查免费额度、账单或等待额度重置。'
    if category == 'rate_limit':
        return f'{provider} 触发限流，请降低并发、增加重试间隔或稍后再试。'
    if category == 'model_not_found':
        return f'{provider} 模型 ID 可能填写错误，请优先使用推荐模型列表中的模型。'
    if category == 'network':
        return f'{provider} 连接不稳定，请检查网络、代理和本机防火墙配置。'
    if category == 'server':
        return f'{provider} 上游服务异常，建议稍后重试并切换备用模型。'
    return f'{provider} 返回未知错误，建议先执行 verify 再使用推荐模型进行探测。'

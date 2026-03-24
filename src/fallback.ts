import { isModelRateLimited, markModelRateLimited, clearModelRateLimited } from './rate-limit';
import { fetchAllModels, isEffectivelyFreeModel } from './models';
import { getCustomModels } from './config';
import type { Model } from './providers/types';
import { getLatestVerification } from './provider-health';
import { isKnownProvider } from './providers/registry';
import { loadModelDictionary, orderModelsByDictionary } from './model-dictionary';

export interface FallbackResult {
  model: string;
  is_fallback: boolean;
  attempted_models: string[];
  fallback_reason?: string;
}

type ExecuteError = {
  status?: number;
  retry_after?: number;
  message?: string;
};

function summarizeFailure(error?: ExecuteError): string {
  if (!error) return '未知错误';

  const message = String(error.message || '');

  if (error.status === 402 || /insufficient credits/i.test(message)) {
    return 'OpenRouter 余额不足（402），请检查账号 credits';
  }

  if (error.status === 429 && /free-models-per-day/i.test(message)) {
    return 'OpenRouter 免费模型日额度已用完（429），请等待重置或充值';
  }

  if (error.status === 429 && /freeusagelimiterror|rate limit exceeded/i.test(message)) {
    return 'OpenCode 免费额度已触发限流（429），请稍后再试';
  }

  if (error.status === 429) {
    return `触发限流（429），建议稍后重试`;
  }

  if (error.status === 401 || error.status === 403) {
    return 'API key 无效或权限不足';
  }

  if (error.status) {
    return `上游返回错误（${error.status}）${message ? `: ${message.slice(0, 120)}` : ''}`;
  }

  return message ? message.slice(0, 160) : '网络或上游异常';
}

// 模型可用性状态（内存中，重启重置）
// 1 = 可用，0 = 最近失败过
const modelAvailability = new Map<string, number>();

function logFallback(message: string): void {
  if (process.env.NODE_ENV === 'test') return;
  console.log(message);
}

function logFallbackError(message: string, error: unknown): void {
  if (process.env.NODE_ENV === 'test') return;
  console.error(message, error);
}

function isModelAvailable(modelId: string): boolean {
  return (modelAvailability.get(modelId) ?? 1) === 1;
}

function markModelAvailable(modelId: string): void {
  modelAvailability.set(modelId, 1);
}

function markModelUnavailable(modelId: string): void {
  modelAvailability.set(modelId, 0);
}

const WHITELIST = ['gpt-4o', 'gpt-4o-mini', 'llama-3.1-8b', 'codestral', 'deepseek', 'qwen'];
const BLACKLIST = ['gpt-3.5', 'tiny', 'deprecated'];

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

function scoreContext(model: Model): number {
  const ctx = model.context_length || 0;
  if (ctx >= 32000) return 10;
  if (ctx >= 16000) return 6;
  if (ctx >= 8000) return 3;
  return 0;
}

function scoreSpeed(model: Model): number {
  const id = model.id.toLowerCase();
  if (id.includes('flash') || id.includes('lite') || model.provider === 'cerebras') return 10;
  if (id.includes('mini') || id.includes('8b')) return 7;
  if (id.includes('70b') || model.provider === 'sambanova') return 3;
  return 5;
}

function scoreDomain(model: Model): number {
  const id = model.id.toLowerCase();
  if (id.includes('codestral') || id.includes('deepseek') || id.includes('qwen')) return 10;
  if (id.includes('gpt-4o-mini') || id.includes('llama-3.1-8b')) return 6;
  return 4;
}

function scoreAbility(model: Model): number {
  const id = model.id.toLowerCase();
  if (id.includes('70b') || id.includes('72b') || id.includes('gpt-4o') || model.provider === 'sambanova') return 20;
  if (id.includes('32b') || id.includes('27b')) return 14;
  if (id.includes('8b') || id.includes('mini')) return 10;
  return 6;
}

function scoreStability(model: Model): number {
  if (model.provider === 'openrouter' || model.provider === 'github') return 12;
  if (model.provider === 'groq' || model.provider === 'mistral') return 11;
  return 9;
}

function scoreModel(model: Model): number {
  const verified = getLatestVerification(model.id)?.verified ?? true;
  const gate = verified && isModelAvailable(model.id) ? 1 : 0;
  const lower = model.id.toLowerCase();
  const whitelistBonus = WHITELIST.some(name => lower.includes(name)) ? 20 : 0;
  const blacklistPenalty = BLACKLIST.some(name => lower.includes(name)) ? 20 : 0;

  const baseScore =
    scoreStability(model) +
    scoreAbility(model) +
    scoreSpeed(model) +
    scoreContext(model) +
    scoreDomain(model) +
    whitelistBonus -
    blacklistPenalty;

  return gate * clamp(baseScore, 0, 100);
}

function rankAllModels(models: Model[]): { model: Model; score: number; available: boolean }[] {
  const orderedModels = orderModelsByDictionary(models, null);
  return orderedModels.map(model => ({
    model,
    score: Math.round(scoreModel(model)),
    available: isModelAvailable(model.id)
  })).sort((a, b) => b.score - a.score);
}

function parseModelProvider(modelId: string): string | null {
  const parts = modelId.split('/');
  if (parts.length < 2) return null;
  return isKnownProvider(parts[0]) ? parts[0] : null;
}

export async function getFallbackChain(preferredModel?: string): Promise<string[]> {
  const chain: string[] = [];

  if (preferredModel) {
    chain.push(preferredModel);
  }

  try {
    const customModels = await getCustomModels();
    for (const custom of customModels) {
      if (!custom.enabled) continue;
      const id = `${custom.provider}/${custom.modelId}`;
      if (!chain.includes(id)) {
        chain.push(id);
      }
    }
  } catch (err) {
    logFallbackError('[Fallback] Failed to load custom models:', err);
  }

  try {
    // 获取所有 provider 的模型
    const allModels = await fetchAllModels();
    const dictionary = await loadModelDictionary();
    
    // 过滤免费模型
    const freeModels = allModels.filter(m => isEffectivelyFreeModel(m));

    const orderedFreeModels = orderModelsByDictionary(freeModels, dictionary);
    const ranked = rankAllModels(orderedFreeModels);
    const preferredProvider = preferredModel ? parseModelProvider(preferredModel) : null;

    if (preferredProvider) {
      const sameProviderVerified = ranked
        .filter(item => item.model.provider === preferredProvider && item.score > 0)
        .map(item => item.model.id);
      for (const modelId of sameProviderVerified) {
        if (!chain.includes(modelId)) chain.push(modelId);
      }
    }

    const topVerified = ranked.find(item => item.score > 0)?.model.id;
    if (topVerified && !chain.includes(topVerified)) {
      chain.push(topVerified);
    }

    const otherVerified = ranked.filter(item => item.score > 0).map(item => item.model.id);
    for (const modelId of otherVerified) {
      if (!chain.includes(modelId)) chain.push(modelId);
    }

    const unverified = ranked.filter(item => item.score === 0).map(item => item.model.id);
    for (const modelId of unverified) {
      if (!chain.includes(modelId)) chain.push(modelId);
    }
  } catch (err) {
    logFallbackError('[Fallback] Failed to get fallback models:', err);
  }

  if (!chain.includes('openrouter/auto:free')) {
    chain.push('openrouter/auto:free');
  }

  return chain;
}

export async function executeWithFallback<T>(
  preferredModel: string | undefined,
  execute: (model: string) => Promise<{ success: boolean; response?: T; error?: ExecuteError }>
): Promise<{ result: T; fallbackInfo: FallbackResult }> {
  const chain = await getFallbackChain(preferredModel);
  const attemptedModels: string[] = [];
  const attemptedErrors: Array<{ model: string; error?: ExecuteError }> = [];
  let isFirstAttempt = true;

  for (const model of chain) {
    if (isModelRateLimited(model)) {
      logFallback(`[Fallback] Skipping ${model} (rate limited)`);
      attemptedModels.push(`${model}(rate_limited)`);
      continue;
    }

    const { success, response, error } = await execute(model);

    if (success && response) {
      // 模型成功，标记为可用
      if (!isModelAvailable(model)) {
        markModelAvailable(model);
        logFallback(`[Fallback] ${model} recovered and now available`);
      }
      await clearModelRateLimited(model);
      
      if (model !== preferredModel) {
        logFallback(`[Fallback] ${preferredModel || 'default'} failed, using ${model}`);
      }
      return {
        result: response,
        fallbackInfo: {
          model,
          is_fallback: model !== preferredModel,
          attempted_models: attemptedModels,
          fallback_reason: model !== preferredModel
            ? `${preferredModel || 'auto-selected'} unavailable, fallback to ${model}`
            : undefined
        }
      };
    }

    // 模型失败，标记为不可用
    markModelUnavailable(model);
    attemptedModels.push(model);
    attemptedErrors.push({ model, error });

    if (isFirstAttempt && chain.length > 1) {
      logFallback(`[Fallback] ${model} failed, trying alternatives...`);
      isFirstAttempt = false;
    }

    // 同时更新 rate-limit 状态（用于持久化记录）
    if (error?.status === 429) {
      await markModelRateLimited(model, 'rate_limit', error.retry_after);
    } else if (error?.status === 503) {
      await markModelRateLimited(model, 'unavailable');
    }
  }

  const last = attemptedErrors[attemptedErrors.length - 1];
  const reason = summarizeFailure(last?.error);
  const attemptedHint = attemptedModels.length ? `；已尝试: ${attemptedModels.join(' -> ')}` : '';
  throw new Error(`无可用模型，请稍后再试。原因：${reason}${attemptedHint}`);
}

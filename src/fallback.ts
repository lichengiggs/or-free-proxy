import { isModelRateLimited, markModelRateLimited } from './rate-limit';
import { fetchAllModels, isEffectivelyFreeModel } from './models';
import { getCustomModels } from './config';
import type { Model } from './providers/types';

export interface FallbackResult {
  model: string;
  is_fallback: boolean;
  attempted_models: string[];
  fallback_reason?: string;
}

// 模型可用性状态（内存中，重启重置）
// 1 = 可用，0 = 最近失败过
const modelAvailability = new Map<string, number>();

function isModelAvailable(modelId: string): boolean {
  return (modelAvailability.get(modelId) ?? 1) === 1;
}

function markModelAvailable(modelId: string): void {
  modelAvailability.set(modelId, 1);
}

function markModelUnavailable(modelId: string): void {
  modelAvailability.set(modelId, 0);
}

const PROVIDER_TRUST_SCORES: Record<string, number> = {
  google: 30, 'meta-llama': 30, mistralai: 30, deepseek: 30,
  nvidia: 30, qwen: 30, groq: 30, opencode: 20
};

const PARAM_SCALE_SCORES = [
  { min: 70, score: 30 },
  { min: 30, score: 25 },
  { min: 13, score: 15 },
  { min: 7, score: 10 },
  { min: 0, score: 5 }
];

function calculateModelScore(model: Model): number {
  let score = 0;
  
  score += Math.min((model.context_length || 0) / 32000, 1) * 40;
  
  const paramMatch = model.name.match(/(\d+(?:\.\d+)?)\s*[bB]\b/);
  if (paramMatch) {
    const params = parseFloat(paramMatch[1]);
    const paramConfig = PARAM_SCALE_SCORES.find(p => params >= p.min)!;
    score += paramConfig.score;
  }
  
  score += PROVIDER_TRUST_SCORES[model.provider] || 10;
  
  return isModelAvailable(model.id) ? score : 0;
}

function rankAllModels(models: Model[]): { model: Model; score: number; available: boolean }[] {
  return models.map(model => ({
    model,
    score: Math.round(calculateModelScore(model)),
    available: isModelAvailable(model.id)
  })).sort((a, b) => b.score - a.score);
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
    console.error('[Fallback] Failed to load custom models:', err);
  }

  try {
    // 获取所有 provider 的模型
    const allModels = await fetchAllModels();
    
    // 过滤免费模型
    const freeModels = allModels.filter(m => isEffectivelyFreeModel(m));
    
    const ranked = rankAllModels(freeModels);

    for (const { model } of ranked) {
      // model.id 已经是 provider/model 格式（来自 fetchAllModels）
      if (!chain.includes(model.id)) {
        chain.push(model.id);
      }
    }
  } catch (err) {
    console.error('[Fallback] Failed to get fallback models:', err);
  }

  if (!chain.includes('openrouter/auto:free')) {
    chain.push('openrouter/auto:free');
  }

  return chain;
}

export async function executeWithFallback<T>(
  preferredModel: string | undefined,
  execute: (model: string) => Promise<{ success: boolean; response?: T; error?: { status?: number; retry_after?: number; message?: string } }>
): Promise<{ result: T; fallbackInfo: FallbackResult }> {
  const chain = await getFallbackChain(preferredModel);
  const attemptedModels: string[] = [];
  let isFirstAttempt = true;

  for (const model of chain) {
    if (isModelRateLimited(model)) {
      console.log(`[Fallback] Skipping ${model} (rate limited)`);
      attemptedModels.push(`${model}(rate_limited)`);
      continue;
    }

    const { success, response, error } = await execute(model);

    if (success && response) {
      // 模型成功，标记为可用
      if (!isModelAvailable(model)) {
        markModelAvailable(model);
        console.log(`[Fallback] ${model} recovered and now available`);
      }
      
      if (model !== preferredModel) {
        console.log(`[Fallback] ${preferredModel || 'default'} failed, using ${model}`);
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

    if (isFirstAttempt && chain.length > 1) {
      console.log(`[Fallback] ${model} failed, trying alternatives...`);
      isFirstAttempt = false;
    }

    // 同时更新 rate-limit 状态（用于持久化记录）
    if (error?.status === 429) {
      await markModelRateLimited(model, 'rate_limit', error.retry_after);
    } else if (error?.status === 503) {
      await markModelRateLimited(model, 'unavailable');
    }
  }

  throw new Error('无可用模型，请稍后再试');
}

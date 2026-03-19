import { isModelRateLimited, markModelRateLimited } from './rate-limit';
import { fetchModels, filterFreeModels, rankModels } from './models';

export interface FallbackResult {
  model: string;
  is_fallback: boolean;
  attempted_models: string[];
  fallback_reason?: string;
}

export async function getFallbackChain(preferredModel?: string): Promise<string[]> {
  const chain: string[] = [];

  if (preferredModel) {
    chain.push(preferredModel);
  }

  try {
    const models = await fetchModels();
    const freeModels = filterFreeModels(models);
    const ranked = rankModels(freeModels);

    for (const { model } of ranked) {
      if (!chain.includes(model.id)) {
        chain.push(model.id);
      }
    }
  } catch (err) {
    console.error('[Fallback] Failed to get fallback models:', err);
  }

  if (!chain.includes('openrouter/free')) {
    chain.push('openrouter/free');
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

    attemptedModels.push(model);

    if (isFirstAttempt && chain.length > 1) {
      console.log(`[Fallback] ${model} failed, trying alternatives...`);
      isFirstAttempt = false;
    }

    if (error?.status === 429) {
      await markModelRateLimited(model, 'rate_limit', error.retry_after);
    } else if (error?.status === 503) {
      await markModelRateLimited(model, 'unavailable');
    }
  }

  throw new Error(`All models failed. Attempted: ${attemptedModels.join(', ')}`);
}
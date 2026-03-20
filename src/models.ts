import { ENV, fetchWithTimeout } from './config';
import { PROVIDERS } from './providers/registry';
import type { Model, ModelScore as ProviderModelScore } from './providers/types';

export interface OpenRouterModel {
  id: string;
  name: string;
  description: string;
  context_length: number;
  pricing: {
    prompt: string;
    completion: string;
  };
}

let cachedModels: OpenRouterModel[] = [];
let lastFetchTime = 0;
const CACHE_TTL = 60 * 60 * 1000;

export async function fetchModels(forceRefresh = false): Promise<OpenRouterModel[]> {
  const now = Date.now();
  if (!forceRefresh && cachedModels.length && now - lastFetchTime < CACHE_TTL) {
    return cachedModels;
  }

  const response = await fetchWithTimeout(`${ENV.OPENROUTER_BASE_URL}/models`, {
    headers: {
      'Authorization': `Bearer ${ENV.OPENROUTER_API_KEY}`,
      'HTTP-Referer': 'http://localhost:8765',
      'X-Title': 'OpenRouter Free Proxy'
    }
  });

  if (!response.ok) {
    const errMsg = `Failed to fetch models: ${response.statusText}`;
    console.error(`[${new Date().toISOString()}] ${errMsg}`);
    throw new Error(errMsg);
  }

  const data = (await response.json()) as { data: OpenRouterModel[] };
  cachedModels = data.data;
  lastFetchTime = now;
  return cachedModels;
}

export function filterFreeModels(models: OpenRouterModel[]): OpenRouterModel[] {
  return models
    .filter(model => {
      if (model.id.endsWith(':free')) return true;
      const promptCost = parseFloat(model.pricing?.prompt || '0');
      const completionCost = parseFloat(model.pricing?.completion || '0');
      if (promptCost === 0 && completionCost === 0) return true;
      return false;
    })
    .sort((a, b) => a.name.localeCompare(b.name));
}

export interface ModelScore {
  model: OpenRouterModel;
  score: number;
  reasons: string[];
}

const TRUSTED_PROVIDERS = [
  'google', 'meta-llama', 'mistralai', 'deepseek',
  'nvidia', 'qwen', 'microsoft', 'allenai',
  'groq', 'minimax', 'glm', 'stepfun', 'mimo'
];

export async function fetchAllModels(): Promise<Model[]> {
  const allModels: Model[] = [];

  for (const provider of PROVIDERS) {
    const key = process.env[provider.apiKeyEnv];
    if (!key) continue;

    try {
      const response = await fetchWithTimeout(`${provider.baseURL}/models`, {
        headers: { 'Authorization': `Bearer ${key}` }
      });

      if (!response.ok) continue;

      const data = await response.json() as { data?: Array<{ id: string; name?: string; context_length?: number; pricing?: { prompt?: string | number; completion?: string | number } }> };
      const models: Model[] = (data.data || []).map((m) => ({
        id: m.id,
        name: m.name || m.id,
        provider: provider.name,
        context_length: m.context_length,
        pricing: {
          prompt: m.pricing?.prompt || '0',
          completion: m.pricing?.completion || '0'
        }
      }));

      const prefixedModels = models.map(m => ({
        ...m,
        id: `${provider.name}/${m.id}`,
        provider: provider.name
      }));

      allModels.push(...prefixedModels);
    } catch (err) {
      console.error(`[${new Date().toISOString()}] Failed to fetch models from ${provider.name}:`, err);
    }
  }

  return allModels;
}

const PARAM_SCORES = [
  { min: 70, score: 20, label: '大参数' },
  { min: 30, score: 15, label: '中参数' },
  { min: 13, score: 10, label: '标准参数' },
  { min: 7, score: 5, label: '轻量参数' },
  { min: 0, score: 2, label: '小参数' }
];

export function extractParameterScore(name: string): { score: number; reason?: string } {
  const match = name.match(/(\d+(?:\.\d+)?)\s*[bB]\b/);
  if (!match) return { score: 0 };

  const params = parseFloat(match[1]);
  const config = PARAM_SCORES.find(p => params >= p.min)!;
  return { score: config.score, reason: `${config.label}(${params}B)` };
}

export function rankModels(models: OpenRouterModel[]): ModelScore[] {
  return models.map(model => {
    let score = 0;
    const reasons: string[] = [];

    // 1. Context length scoring (0-40 points)
    const contextLength = model.context_length || 0;
    const contextScore = Math.min(contextLength / 32000, 1) * 40;
    score += contextScore;
    if (contextScore >= 40) reasons.push('超长上下文(32k+)');
    else if (contextScore >= 20) reasons.push('长上下文(16k+)');

    // 2. Provider trust scoring (0-30 points)
    const provider = model.id.split('/')[0].toLowerCase();
    const providerIndex = TRUSTED_PROVIDERS.indexOf(provider);
    const providerScore = providerIndex >= 0
      ? (1 - providerIndex / TRUSTED_PROVIDERS.length) * 30
      : 10;
    score += providerScore;
    if (providerScore >= 25) reasons.push('知名提供商');

    // 3. Parameter scoring (0-20 points)
    const paramScore = extractParameterScore(model.name);
    score += paramScore.score;
    if (paramScore.reason) reasons.push(paramScore.reason);

    return { model, score: Math.round(score), reasons };
  }).sort((a, b) => b.score - a.score);
}

export function getRecommendedModel(models: OpenRouterModel[]): ModelScore | null {
  const ranked = rankModels(models);
  return ranked[0] || null;
}

export function isEffectivelyFreeModel(model: Pick<Model, 'id' | 'provider' | 'pricing'>): boolean {
  if (model.provider === 'opencode') {
    return model.id.endsWith('-free') || model.id.includes('-free-');
  }

  const prompt = parseFloat(String(model.pricing?.prompt || '0'));
  const completion = parseFloat(String(model.pricing?.completion || '0'));
  return prompt === 0 && completion === 0;
}

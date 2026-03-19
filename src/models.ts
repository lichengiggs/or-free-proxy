import { ENV, fetchWithTimeout } from './config';

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
  'nvidia', 'qwen', 'microsoft', 'allenai'
];

export function extractParameterScore(name: string): { score: number; reason?: string } {
  const match = name.match(/(\d+(?:\.\d+)?)\s*[bB]\b/);
  if (!match) return { score: 0 };

  const params = parseFloat(match[1]);

  if (params >= 70) {
    return { score: 20, reason: `大参数(${params}B)` };
  } else if (params >= 30) {
    return { score: 15, reason: `中参数(${params}B)` };
  } else if (params >= 13) {
    return { score: 10, reason: `标准参数(${params}B)` };
  } else if (params >= 7) {
    return { score: 5, reason: `轻量参数(${params}B)` };
  }

  return { score: 2, reason: `小参数(${params}B)` };
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

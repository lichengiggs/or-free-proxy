import { ENV, fetchWithTimeout, getProviderKey } from './config';
import { PROVIDERS } from './providers/registry';
import type { Model, Provider } from './providers/types';

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
const MULTI_PROVIDER_CACHE_TTL = 5 * 60 * 1000;

const providerModelCache = new Map<string, { models: Model[]; fetchedAt: number }>();

export function clearModelDiscoveryCache(): void {
  providerModelCache.clear();
}

export const __MODEL_TEST_ONLY__ = {
  clearProviderModelCache: clearModelDiscoveryCache
};

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
  const allResults = await Promise.all(
    PROVIDERS.map(async provider => {
      const key = getProviderKey(provider.name);
      if (!key) return [];
      return fetchProviderModels(provider, key);
    })
  );

  return allResults.flat();
}

type RawProviderModel = {
  id: string;
  name?: string;
  slug?: string;
  model?: string;
  context_length?: number;
  pricing?: { prompt?: string | number; completion?: string | number };
  task?: string;
  object?: string;
  type?: string;
  friendly_name?: string;
  model_family?: string;
  publisher?: string;
  model_version?: number;
  endpoint?: string;
  architecture?: {
    modality?: string;
    input_modalities?: string[];
    output_modalities?: string[];
  };
};

const GEMINI_FALLBACK_MODELS = [
  {
    id: 'gemini/gemini-3.1-flash-lite-preview',
    name: 'Gemini 3.1 Flash Lite Preview',
    provider: 'gemini',
    pricing: { prompt: '0', completion: '0' }
  },
  {
    id: 'gemini/gemma-3-27b-it',
    name: 'Gemma 3 27B',
    provider: 'gemini',
    pricing: { prompt: '0', completion: '0' }
  }
] as const;

function normalizeGeminiModelId(id: string): string {
  return id.replace(/^models\//, '');
}

function normalizeGithubModelId(id: string): string {
  const match = id.match(/\/models\/([^/]+)\//i);
  if (match?.[1]) return match[1];
  const parts = id.split('/').filter(Boolean);
  return parts[parts.length - 1] || id;
}

function normalizeOpenCodeModelId(id: string): string {
  return id.replace(/^models\//, '');
}

function getRawModelId(model: Partial<RawProviderModel>): string {
  return String(model.id || model.name || model.model || model.slug || '');
}

export function normalizeProviderModelId(providerName: string, modelId: string): string {
  if (providerName === 'gemini') return normalizeGeminiModelId(modelId);
  if (providerName === 'github') return normalizeGithubModelId(modelId);
  if (providerName === 'opencode') return normalizeOpenCodeModelId(modelId);
  return modelId;
}

export function resolveProviderModelName(providerName: string, model: RawProviderModel): string {
  const normalizedId = normalizeProviderModelId(providerName, getRawModelId(model));
  return model.name || model.friendly_name || normalizedId;
}

function isOpenCodeFreeModel(model: RawProviderModel): boolean {
  const id = String(model.id || '').toLowerCase();
  const name = String(model.name || model.friendly_name || '').toLowerCase();
  const endpoint = String(model.endpoint || '').toLowerCase();
  return id.includes('free') || name.includes('free') || endpoint.includes('/chat/completions') || endpoint.includes('/responses');
}

function buildOpenCodeFallbackModels(): Model[] {
  return [
    {
      id: 'opencode/mimo-v2-pro-free',
      name: 'MiMo V2 Pro Free',
      provider: 'opencode',
      pricing: { prompt: '0', completion: '0' }
    }
  ];
}

function buildGithubFallbackModels(): Model[] {
  return [
    {
      id: 'github/gpt-4o-mini',
      name: 'GPT-4o Mini',
      provider: 'github',
      pricing: { prompt: '0', completion: '0' }
    }
  ];
}

function buildGeminiFallbackModels(): Model[] {
  return GEMINI_FALLBACK_MODELS.map(model => ({ ...model }));
}

export function isChatModel(model: RawProviderModel): boolean {
  const taskSignals = `${model.task || ''} ${model.object || ''} ${model.type || ''}`.toLowerCase();
  if (taskSignals.includes('chat') || taskSignals.includes('completion')) {
    return true;
  }

  const modality = String(model.architecture?.modality || '').toLowerCase();
  if (modality.includes('text->text') || modality.includes('text_to_text')) {
    return true;
  }

  const id = String(model.id || '').toLowerCase();
  return ['chat', 'instruct', 'gpt', 'gemini', 'llama', 'qwen', 'deepseek', 'mistral', 'claude']
    .some(keyword => id.includes(keyword));
}

export async function fetchProviderModels(provider: Provider, key: string): Promise<Model[]> {
  const cached = providerModelCache.get(provider.name);
  const now = Date.now();
  if (cached && now - cached.fetchedAt < MULTI_PROVIDER_CACHE_TTL) {
    return cached.models;
  }

  try {
    const response = await fetchWithTimeout(`${provider.baseURL}/models`, {
      headers: provider.name === 'gemini'
        ? { 'x-goog-api-key': key }
        : { Authorization: `Bearer ${key}` }
    });

    if (!response.ok) {
      if (provider.name === 'gemini') return buildGeminiFallbackModels();
      if (provider.name === 'github') return buildGithubFallbackModels();
      if (provider.name === 'opencode') return buildOpenCodeFallbackModels();
      providerModelCache.set(provider.name, { models: [], fetchedAt: now });
      return [];
    }

    const payload = await response.json() as { data?: RawProviderModel[]; models?: RawProviderModel[]; items?: RawProviderModel[] } | RawProviderModel[];
    const rawModels = Array.isArray(payload)
      ? payload
      : (payload.data || payload.models || payload.items || []);

    const models = rawModels
      .filter(model => {
        const rawId = getRawModelId(model);
        if (provider.name === 'gemini') {
          const normalized = normalizeGeminiModelId(rawId);
          return normalized === 'gemini-3.1-flash-lite-preview' || normalized === 'gemma-3-27b-it';
        }
        if (provider.name === 'github') {
          const family = String(model.model_family || '').toLowerCase();
          const name = String(model.friendly_name || model.name || rawId).toLowerCase();
          const task = String(model.task || '').toLowerCase();
          const normalizedId = normalizeGithubModelId(rawId).toLowerCase();
          return task.includes('chat')
            || family.includes('gpt')
            || family.includes('llama')
            || family.includes('mistral')
            || name.includes('gpt')
            || name.includes('llama')
            || name.includes('mistral')
            || name.includes('phi')
            || name.includes('mini')
            || normalizedId.includes('gpt')
            || normalizedId.includes('llama')
            || normalizedId.includes('mistral')
            || normalizedId.includes('phi')
            || normalizedId.includes('mini');
        }
        if (provider.name === 'opencode') {
          return isOpenCodeFreeModel(model);
        }
        return isChatModel(model);
      })
      .map((model): Model => ({
        id: `${provider.name}/${normalizeProviderModelId(provider.name, getRawModelId(model))}`,
        name: resolveProviderModelName(provider.name, {
          ...model,
          id: getRawModelId(model)
        } as RawProviderModel),
        provider: provider.name,
        context_length: model.context_length,
        pricing: {
          prompt: model.pricing?.prompt || '0',
          completion: model.pricing?.completion || '0'
        }
      }));

    if (provider.name === 'github' && models.length === 0) {
      return buildGithubFallbackModels();
    }

    providerModelCache.set(provider.name, { models, fetchedAt: now });
    return models;
  } catch (err) {
    console.error(`[${new Date().toISOString()}] Failed to fetch models from ${provider.name}:`, err);
    if (provider.name === 'gemini') return buildGeminiFallbackModels();
    if (provider.name === 'github') return buildGithubFallbackModels();
    if (provider.name === 'opencode') return buildOpenCodeFallbackModels();
    return [];
  }
}

export function normalizeProviderModels(models: Model[]): Model[] {
  const seen = new Set<string>();
  const result: Model[] = [];

  for (const model of models) {
    if (model.provider === 'gemini') {
      if (!seen.has(model.id)) {
        seen.add(model.id);
        result.push(model);
      }
      continue;
    }

    if (seen.has(model.id)) continue;
    seen.add(model.id);
    result.push(model);
  }

  return result;
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

import { fetchWithTimeout, getProviderKey } from './config';
import { PROVIDERS } from './providers/registry';

export type VerifyReason = 'auth_failed' | 'network_error' | 'model_unavailable';

export interface ModelAvailability {
  id: string;
  provider: string;
  verified: boolean;
  reason?: VerifyReason;
  lastCheckedAt: number;
}

const latestVerification = new Map<string, ModelAvailability>();

export function buildProviderHeaders(provider: string, apiKey: string): Record<string, string> {
  if (provider === 'gemini') {
    return {
      'x-goog-api-key': apiKey,
      'Content-Type': 'application/json'
    };
  }

  const headers: Record<string, string> = {
    Authorization: `Bearer ${apiKey}`,
    'Content-Type': 'application/json'
  };

  if (provider === 'openrouter') {
    headers['HTTP-Referer'] = 'http://localhost:8765';
    headers['X-Title'] = 'OpenRouter Free Proxy';
  }

  return headers;
}

export function normalizeVerificationModelId(provider: string, modelId: string): string {
  if (provider === 'gemini') {
    return modelId.startsWith('models/') ? modelId : `models/${modelId}`;
  }

  return modelId;
}

export async function validateProviderKey(provider: string): Promise<{ ok: boolean; reason?: VerifyReason }> {
  const providerConfig = PROVIDERS.find(p => p.name === provider);
  if (!providerConfig) return { ok: false, reason: 'model_unavailable' };

  const key = getProviderKey(provider);
  if (!key) return { ok: false, reason: 'auth_failed' };

  try {
    const response = await fetchWithTimeout(`${providerConfig.baseURL}/models`, {
      headers: buildProviderHeaders(provider, key)
    }, 10000);

    if (response.status === 401 || response.status === 403) {
      return { ok: false, reason: 'auth_failed' };
    }

    return { ok: response.ok, reason: response.ok ? undefined : 'model_unavailable' };
  } catch {
    return { ok: false, reason: 'network_error' };
  }
}

export async function validateProviderKeyWithKey(
  provider: string,
  apiKey: string,
  baseURL: string
): Promise<{ ok: boolean; reason?: VerifyReason }> {
  try {
    const response = await fetchWithTimeout(`${baseURL}/models`, {
      headers: buildProviderHeaders(provider, apiKey)
    }, 10000);

    if (response.status === 401 || response.status === 403) {
      return { ok: false, reason: 'auth_failed' };
    }

    return { ok: response.ok, reason: response.ok ? undefined : 'model_unavailable' };
  } catch {
    return { ok: false, reason: 'network_error' };
  }
}

export function getLatestVerification(modelId: string): ModelAvailability | undefined {
  return latestVerification.get(modelId);
}

export async function verifyModelAvailability(
  provider: string,
  modelId: string
): Promise<ModelAvailability> {
  const providerConfig = PROVIDERS.find(p => p.name === provider);
  const now = Date.now();

  if (!providerConfig) {
    const reason: VerifyReason = 'model_unavailable';
    const result = {
      id: `${provider}/${modelId}`,
      provider,
      verified: false,
      reason,
      lastCheckedAt: now
    };
    latestVerification.set(result.id, result);
    return result;
  }

  const key = getProviderKey(provider);
  if (!key) {
    const reason: VerifyReason = 'auth_failed';
    const result = {
      id: `${provider}/${modelId}`,
      provider,
      verified: false,
      reason,
      lastCheckedAt: now
    };
    latestVerification.set(result.id, result);
    return result;
  }

  try {
    const response = provider === 'gemini'
      ? await fetchWithTimeout(`${providerConfig.baseURL}/${normalizeVerificationModelId(provider, modelId)}:generateContent`, {
        method: 'POST',
        headers: buildProviderHeaders(provider, key),
        body: JSON.stringify({
          contents: [{ parts: [{ text: 'ping' }] }],
          generationConfig: { maxOutputTokens: 1 }
        })
      }, 12000)
      : await fetchWithTimeout(`${providerConfig.baseURL}/chat/completions`, {
        method: 'POST',
        headers: buildProviderHeaders(provider, key),
        body: JSON.stringify({
          model: modelId,
          messages: [{ role: 'user', content: 'ping' }],
          max_tokens: 1
        })
      }, 12000);

    if (response.ok) {
      const result = {
        id: `${provider}/${modelId}`,
        provider,
        verified: true,
        lastCheckedAt: now
      };
      latestVerification.set(result.id, result);
      return result;
    }

    const reason: VerifyReason = response.status === 401 || response.status === 403
      ? 'auth_failed'
      : 'model_unavailable';

    const result = {
      id: `${provider}/${modelId}`,
      provider,
      verified: false,
      reason,
      lastCheckedAt: now
    };
    latestVerification.set(result.id, result);
    return result;
  } catch {
    const reason: VerifyReason = 'network_error';
    const result = {
      id: `${provider}/${modelId}`,
      provider,
      verified: false,
      reason,
      lastCheckedAt: now
    };
    latestVerification.set(result.id, result);
    return result;
  }
}

import type { Provider, Model, ProviderAdapter, ChatRequest } from '../types';

function normalizeProviderModelId(providerName: string, modelId: string): string {
  if (providerName === 'gemini') {
    return modelId.startsWith('models/') ? modelId : `models/${modelId}`;
  }
  return modelId;
}

function buildChatURL(provider: Provider): string {
  if (provider.name === 'gemini') {
    return `${provider.baseURL}/models/${process.env.GEMINI_MODEL_ID || 'gemini-3.1-flash-lite-preview'}:generateContent`;
  }
  return `${provider.baseURL}/chat/completions`;
}

function buildRequestBody(provider: Provider, request: ChatRequest): unknown {
  if (provider.name === 'gemini') {
    return {
      contents: request.messages.map(message => ({
        role: message.role === 'assistant' ? 'model' : 'user',
        parts: [{ text: String(message.content) }]
      })),
      generationConfig: {
        maxOutputTokens: request.max_tokens,
        temperature: request.temperature
      }
    };
  }

  return {
    ...request,
    model: normalizeProviderModelId(provider.name, request.model)
  };
}

export class OpenAIAdapter implements ProviderAdapter {
  constructor(private provider: Provider) {}

  get name(): string {
    return this.provider.name;
  }

  async validateKey(): Promise<boolean> {
    const key = process.env[this.provider.apiKeyEnv];
    if (!key) return false;

    try {
      const response = await fetch(`${this.provider.baseURL}/models`, {
        headers: this.provider.name === 'gemini'
          ? { 'x-goog-api-key': key }
          : { 'Authorization': `Bearer ${key}` }
      });
      return response.ok;
    } catch {
      return false;
    }
  }

  async getModels(): Promise<Model[]> {
    const key = process.env[this.provider.apiKeyEnv];
    if (!key) return [];

    try {
      const response = await fetch(`${this.provider.baseURL}/models`, {
        headers: this.provider.name === 'gemini'
          ? { 'x-goog-api-key': key }
          : { 'Authorization': `Bearer ${key}` }
      });

      if (!response.ok) return [];

      const data = await response.json();
      return (data.data || data.models || []).map((m: any) => ({
        id: normalizeProviderModelId(this.provider.name, m.id || m.name),
        name: m.name || m.id,
        provider: this.provider.name,
        context_length: m.context_length,
        pricing: m.pricing
      }));
    } catch {
      return [];
    }
  }

  async chat(request: ChatRequest): Promise<Response> {
    const key = process.env[this.provider.apiKeyEnv];

    return fetch(buildChatURL(this.provider), {
      method: 'POST',
      headers: {
        ...(this.provider.name === 'gemini'
          ? { 'x-goog-api-key': key || '' }
          : { 'Authorization': `Bearer ${key}` }),
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(buildRequestBody(this.provider, request))
    });
  }
}

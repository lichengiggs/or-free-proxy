import type { Provider } from './types';

export const PROVIDERS: Provider[] = [
  {
    name: 'openrouter',
    baseURL: 'https://openrouter.ai/api/v1',
    apiKeyEnv: 'OPENROUTER_API_KEY',
    format: 'openai',
    isFree: true
  },
  {
    name: 'groq',
    baseURL: 'https://api.groq.com/openai/v1',
    apiKeyEnv: 'GROQ_API_KEY',
    format: 'openai',
    isFree: true
  },
  {
    name: 'opencode',
    baseURL: 'https://opencode.ai/zen/v1',
    apiKeyEnv: 'OPENCODE_API_KEY',
    format: 'openai',
    isFree: true
  },
  {
    name: 'gemini',
    baseURL: 'https://generativelanguage.googleapis.com/v1beta',
    apiKeyEnv: 'GEMINI_API_KEY',
    format: 'gemini',
    isFree: true
  },
  {
    name: 'github',
    baseURL: 'https://models.github.ai/inference',
    apiKeyEnv: 'GITHUB_MODELS_API_KEY',
    format: 'openai',
    isFree: true
  },
  {
    name: 'mistral',
    baseURL: 'https://api.mistral.ai/v1',
    apiKeyEnv: 'MISTRAL_API_KEY',
    format: 'openai',
    isFree: true
  },
  {
    name: 'cerebras',
    baseURL: 'https://api.cerebras.ai/v1',
    apiKeyEnv: 'CEREBRAS_API_KEY',
    format: 'openai',
    isFree: true
  },
  {
    name: 'sambanova',
    baseURL: 'https://api.sambanova.ai/v1',
    apiKeyEnv: 'SAMBANOVA_API_KEY',
    format: 'openai',
    isFree: true
  }
];

export function getProviderByName(name: string): Provider | undefined {
  return PROVIDERS.find(p => p.name === name);
}

export function isKnownProvider(name: string): boolean {
  return PROVIDERS.some(p => p.name === name);
}

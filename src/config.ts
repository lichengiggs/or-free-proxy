import { readFile, writeFile, chmod } from 'node:fs/promises';
import { existsSync, readFileSync } from 'node:fs';
import dotenv from 'dotenv';
import { fetch as undiciFetch, ProxyAgent } from 'undici';

dotenv.config();

// 自动检测并配置 HTTP 代理
const proxyUrl = process.env.https_proxy || process.env.http_proxy || process.env.HTTPS_PROXY || process.env.HTTP_PROXY;
const proxyAgent = proxyUrl ? new ProxyAgent(proxyUrl) : null;

// 文件写入锁，防止并发写入冲突
let writeLock = Promise.resolve();

const ENV_PATH = '.env';

export interface Config {
  default_model: string;
  preferred_model?: string;
  customProviders?: CustomProvider[];
  customModels?: CustomModel[];
}

export interface CustomProvider {
  name: string;
  baseURL: string;
  apiKey: string;
}

export interface CustomModel {
  provider: string;
  modelId: string;
  addedAt: number;
  priority?: number;
  enabled?: boolean;
  lastVerifiedAt?: number;
}

const CONFIG_PATH = 'config.json';
const DEFAULT_CONFIG: Config = {
  default_model: 'openrouter/auto:free'
};

let cachedConfig: Config | null = null;

export async function getConfig(): Promise<Config> {
  if (cachedConfig) return cachedConfig;
  
  if (!existsSync(CONFIG_PATH)) {
    await writeFile(CONFIG_PATH, JSON.stringify(DEFAULT_CONFIG, null, 2));
    cachedConfig = DEFAULT_CONFIG;
    return cachedConfig;
  }

  try {
    const content = await readFile(CONFIG_PATH, 'utf-8');
    cachedConfig = JSON.parse(content) as Config;
    return cachedConfig;
  } catch {
    await writeFile(CONFIG_PATH, JSON.stringify(DEFAULT_CONFIG, null, 2));
    cachedConfig = DEFAULT_CONFIG;
    return cachedConfig;
  }
}

export async function setConfig(config: Partial<Config>): Promise<Config> {
  const currentConfig = await getConfig();
  const newConfig = { ...currentConfig, ...config };
  await writeFile(CONFIG_PATH, JSON.stringify(newConfig, null, 2));
  cachedConfig = newConfig;
  return newConfig;
}

export const ENV = {
  OPENROUTER_API_KEY: process.env.OPENROUTER_API_KEY || '',
  OPENROUTER_BASE_URL: process.env.OPENROUTER_BASE_URL || 'https://openrouter.ai/api/v1',
  GROQ_API_KEY: process.env.GROQ_API_KEY || '',
  OPENCODE_API_KEY: process.env.OPENCODE_API_KEY || '',
  GEMINI_API_KEY: process.env.GEMINI_API_KEY || '',
  GITHUB_MODELS_API_KEY: process.env.GITHUB_MODELS_API_KEY || '',
  MISTRAL_API_KEY: process.env.MISTRAL_API_KEY || '',
  CEREBRAS_API_KEY: process.env.CEREBRAS_API_KEY || '',
  SAMBANOVA_API_KEY: process.env.SAMBANOVA_API_KEY || '',
  PORT: Number(process.env.PORT) || 8765
};

function getRuntimeEnv<T extends string | number>(key: string, fallback: T): T {
  const value = process.env[key];
  if (typeof fallback === 'number') {
    return (value ? Number(value) : fallback) as T;
  }
  return (value || fallback) as T;
}

async function hardenEnvFilePermissions(): Promise<void> {
  if (process.platform === 'win32' || !existsSync(ENV_PATH)) return;
  try {
    await chmod(ENV_PATH, 0o600);
  } catch {
    // 忽略权限设置失败，不影响主流程
  }
}

const PROVIDER_ENV_MAP: Record<string, string> = {
  openrouter: 'OPENROUTER_API_KEY',
  groq: 'GROQ_API_KEY',
  opencode: 'OPENCODE_API_KEY',
  gemini: 'GEMINI_API_KEY',
  github: 'GITHUB_MODELS_API_KEY',
  mistral: 'MISTRAL_API_KEY',
  cerebras: 'CEREBRAS_API_KEY',
  sambanova: 'SAMBANOVA_API_KEY'
};

export function getProviderKey(provider: string): string | undefined {
  const envKey = PROVIDER_ENV_MAP[provider];
  if (!envKey) return undefined;

  const runtimeValue = process.env[envKey]?.trim();
  if (runtimeValue) return runtimeValue;

  if (!existsSync(ENV_PATH)) return undefined;

  try {
    const content = readFileSync(ENV_PATH, 'utf-8');
    const match = content.match(new RegExp(`^${envKey}=(.+)$`, 'm'));
    const fileValue = match?.[1]?.trim();
    if (fileValue) {
      process.env[envKey] = fileValue;
      return fileValue;
    }
  } catch {
    return undefined;
  }

  return undefined;
}

export interface MultiProviderKeyStatus {
  [provider: string]: {
    configured: boolean;
    masked: string | null;
  };
}

async function getProviderStatus(provider: string): Promise<{ configured: boolean; masked: string | null }> {
  const key = getProviderKey(provider);
  if (key) {
    return { configured: true, masked: maskApiKey(key) };
  }

  if (!existsSync(ENV_PATH)) {
    return { configured: false, masked: null };
  }

  const content = await readFile(ENV_PATH, 'utf-8');
  const envKey = PROVIDER_ENV_MAP[provider];
  const match = content.match(new RegExp(`${envKey}=(.+)`));
  return {
    configured: !!match,
    masked: match ? maskApiKey(match[1].trim()) : null
  };
}

export async function getAllProviderKeysStatus(): Promise<MultiProviderKeyStatus> {
  const providers = ['openrouter', 'groq', 'opencode', 'gemini', 'github', 'mistral', 'cerebras', 'sambanova'];
  const status: MultiProviderKeyStatus = {};

  for (const provider of providers) {
    status[provider] = await getProviderStatus(provider);
  }

  return status;
}

export async function saveProviderKey(provider: string, key: string): Promise<void> {
  if (!key || key.trim().length === 0) {
    throw new Error('API key cannot be empty');
  }

  const trimmedKey = key.trim();
  const envKey = PROVIDER_ENV_MAP[provider];

  if (!envKey) {
    throw new Error(`Unknown provider: ${provider}`);
  }

  // 使用锁确保串行写入
  writeLock = writeLock.then(async () => {
    const keyLine = `${envKey}=${trimmedKey}`;
    const fileExists = existsSync(ENV_PATH);

    if (fileExists) {
      const content = await readFile(ENV_PATH, 'utf-8');
      const lines = content.split('\n').filter(line => line && !line.startsWith(`${envKey}=`));
      lines.push(keyLine);
      await writeFile(ENV_PATH, lines.join('\n') + '\n', 'utf-8');
    } else {
      await writeFile(ENV_PATH, keyLine + '\n', 'utf-8');
    }
    await hardenEnvFilePermissions();
  });

  await writeLock;
  process.env[envKey] = trimmedKey;
}

export async function saveCustomProvider(provider: CustomProvider): Promise<void> {
  const config = await getConfig();
  const customProviders = config.customProviders || [];
  const existingIndex = customProviders.findIndex(p => p.name === provider.name);
  if (existingIndex >= 0) {
    customProviders[existingIndex] = provider;
  } else {
    customProviders.push(provider);
  }
  await setConfig({ ...config, customProviders });
}

export async function saveCustomModel(model: CustomModel): Promise<void> {
  const config = await getConfig();
  const customModels = config.customModels || [];
  const existingIndex = customModels.findIndex(m => m.provider === model.provider && m.modelId === model.modelId);
  const normalized: CustomModel = {
    ...model,
    priority: Number.isFinite(model.priority) ? model.priority : 100,
    enabled: model.enabled !== false
  };
  if (existingIndex >= 0) {
    customModels[existingIndex] = normalized;
  } else {
    customModels.push(normalized);
  }
  await setConfig({ ...config, customModels });
}

export async function getCustomModels(): Promise<CustomModel[]> {
  const config = await getConfig();
  return (config.customModels || []).slice().sort((a, b) => (a.priority ?? 100) - (b.priority ?? 100));
}

export async function deleteCustomModel(provider: string, modelId: string): Promise<boolean> {
  const config = await getConfig();
  const customModels = config.customModels || [];
  const next = customModels.filter(m => !(m.provider === provider && m.modelId === modelId));
  if (next.length === customModels.length) return false;
  await setConfig({ ...config, customModels: next });
  return true;
}

export interface ApiKeyStatus {
  configured: boolean;
  masked: string | null;
}

export function maskApiKey(key: string | null): string | null {
  if (!key) {
    return null;
  }
  const prefixLen = key.startsWith('sk-or-') ? 6 :
                     key.startsWith('gsk-') ? 4 : 3;
  const prefix = key.slice(0, prefixLen);
  const remaining = key.slice(prefixLen);
  if (remaining.length <= 3) {
    return `${prefix}***${remaining}`;
  }
  return `${prefix}***${remaining.slice(-3)}`;
}

export async function saveApiKey(key: string): Promise<void> {
  if (!key || key.trim().length === 0) {
    throw new Error('API key cannot be empty');
  }
  
  const trimmedKey = key.trim();
  if (!trimmedKey.startsWith('sk-')) {
    throw new Error('Invalid API key format');
  }
  
  await saveProviderKey('openrouter', trimmedKey);
}

export async function getApiKeyStatus(): Promise<ApiKeyStatus> {
  const key = getRuntimeEnv('OPENROUTER_API_KEY', '');
  if (!key && existsSync(ENV_PATH)) {
    try {
      const content = await readFile(ENV_PATH, 'utf-8');
      const match = content.match(/OPENROUTER_API_KEY=(.+)/);
      if (match && match[1]) {
        return { configured: true, masked: maskApiKey(match[1].trim()) };
      }
    } catch {}
  }
  if (!key) {
    return { configured: false, masked: null };
  }
  return { configured: true, masked: maskApiKey(key) };
}

export async function fetchWithTimeout(
  url: string,
  options: RequestInit = {},
  timeout = 10000
): Promise<Response> {
  const controller = new AbortController();
  const id = setTimeout(() => controller.abort(), timeout);
  
  try {
    // 如果有代理配置，使用 undici 的 fetch
    if (proxyAgent) {
      const undiciOptions: any = {
        method: options.method,
        headers: options.headers,
        body: options.body,
        dispatcher: proxyAgent,
        signal: controller.signal
      };
      return await undiciFetch(url, undiciOptions) as unknown as Response;
    }
    // 否则使用原生 fetch
    return await fetch(url, { ...options, signal: controller.signal });
  } finally {
    clearTimeout(id);
  }
}

import { readFile, writeFile } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import dotenv from 'dotenv';

dotenv.config();

const ENV_PATH = '.env';

export interface Config {
  default_model: string;
  preferred_model?: string;
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
  PORT: Number(process.env.PORT) || 8765
};

export interface ApiKeyStatus {
  configured: boolean;
  masked: string | null;
}

export function maskApiKey(key: string | null): string | null {
  if (!key) {
    return null;
  }
  const remaining = key.slice(3);
  if (remaining.length <= 3) {
    return `sk-****${remaining}`;
  }
  return `sk-****${remaining.slice(-3)}`;
}

export async function saveApiKey(key: string): Promise<void> {
  if (!key || key.trim().length === 0) {
    throw new Error('API key cannot be empty');
  }
  
  const trimmedKey = key.trim();
  if (!trimmedKey.startsWith('sk-')) {
    throw new Error('Invalid API key format');
  }
  
  const keyLine = `OPENROUTER_API_KEY=${trimmedKey}\n`;
  const fileExists = existsSync(ENV_PATH);
  
  if (fileExists) {
    const content = await readFile(ENV_PATH, 'utf-8');
    const lines = content.split('\n').filter(line => !line.startsWith('OPENROUTER_API_KEY='));
    await writeFile(ENV_PATH, lines.join('\n') + keyLine, 'utf-8');
  } else {
    await writeFile(ENV_PATH, keyLine, 'utf-8');
  }
  
  process.env.OPENROUTER_API_KEY = trimmedKey;
}

export async function getApiKeyStatus(): Promise<ApiKeyStatus> {
  const key = ENV.OPENROUTER_API_KEY;
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
    return await fetch(url, { ...options, signal: controller.signal });
  } finally {
    clearTimeout(id);
  }
}

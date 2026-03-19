import { existsSync, readFileSync, writeFileSync, readdirSync, mkdirSync } from 'node:fs';
import { homedir } from 'node:os';
import { join } from 'node:path';

const OPENCLAW_DIR = process.env.OPENCLAW_TEST_DIR || join(homedir(), '.openclaw');
const OPENCLAW_CONFIG_PATH = join(OPENCLAW_DIR, 'openclaw.json');

export interface OpenClawConfigResult {
  exists: boolean;
  isValid: boolean;
  content?: object;
  path?: string;
}

export interface ConfigureResult {
  success: boolean;
  backup?: string | null;
  error?: string;
}

export async function detectOpenClawConfig(): Promise<OpenClawConfigResult> {
  const result: OpenClawConfigResult = {
    exists: false,
    isValid: false,
    path: OPENCLAW_CONFIG_PATH
  };

  if (!existsSync(OPENCLAW_CONFIG_PATH)) {
    return result;
  }

  result.exists = true;

  try {
    const content = readFileSync(OPENCLAW_CONFIG_PATH, 'utf-8');
    result.content = JSON.parse(content);
    result.isValid = true;
  } catch {
    result.isValid = false;
  }

  return result;
}

export async function mergeConfig(): Promise<ConfigureResult> {
  const status = await detectOpenClawConfig();
  
  if (status.exists && !status.isValid) {
    return { success: false, error: 'Invalid JSON' };
  }

  let existingConfig: any = {};
  
  if (status.exists && status.isValid) {
    existingConfig = status.content as object;
  }

  const files = existsSync(OPENCLAW_DIR) ? readdirSync(OPENCLAW_DIR) : [];
  const existingBackups = files.filter(f => /^openclaw\.bak\d+$/.test(f));
  const nextNum = existingBackups.length > 0
    ? Math.max(...existingBackups.map(f => parseInt(f.replace('openclaw.bak', '')) || 0)) + 1
    : 1;
  const backupPath = join(OPENCLAW_DIR, `openclaw.bak${nextNum}`);
  
  if (status.exists) {
    const content = readFileSync(OPENCLAW_CONFIG_PATH, 'utf-8');
    writeFileSync(backupPath, content, 'utf-8');
  } else {
    if (!existsSync(OPENCLAW_DIR)) {
      mkdirSync(OPENCLAW_DIR, { recursive: true });
    }
  }

  const baseUrl = `http://localhost:${process.env.PORT || 8765}/v1`;
  
  const newConfig: any = JSON.parse(JSON.stringify(existingConfig));
  
  if (!newConfig.models) {
    newConfig.models = {};
  }
  if (!newConfig.models.providers) {
    newConfig.models.providers = {};
  }
  
  newConfig.models.providers.free_proxy = {
    baseUrl,
    apiKey: 'any_string',
    api: 'openai-completions',
    models: [{ id: 'auto', name: 'auto' }]
  };

  if (!newConfig.agents) {
    newConfig.agents = {};
  }
  if (!newConfig.agents.defaults) {
    newConfig.agents.defaults = {};
  }
  if (!newConfig.agents.defaults.models) {
    newConfig.agents.defaults.models = {};
  }
  
  newConfig.agents.defaults.models['free_proxy/auto'] = {};

  writeFileSync(OPENCLAW_CONFIG_PATH, JSON.stringify(newConfig, null, 2), 'utf-8');

  return {
    success: true,
    backup: status.exists ? backupPath : null
  };
}

export async function listBackups(): Promise<string[]> {
  if (!existsSync(OPENCLAW_DIR)) {
    return [];
  }

  const files = readdirSync(OPENCLAW_DIR);
  const backups = files
    .filter(f => /^openclaw\.bak\d+$/.test(f))
    .sort((a, b) => {
      const numA = parseInt(a.replace('openclaw.bak', '')) || 0;
      const numB = parseInt(b.replace('openclaw.bak', '')) || 0;
      return numB - numA;
    });
  
  return backups;
}

export async function restoreBackup(backupName: string): Promise<{ success: boolean; error?: string }> {
  const backupPath = join(OPENCLAW_DIR, backupName);
  
  if (!existsSync(backupPath)) {
    return { success: false, error: 'Backup file not found' };
  }

  try {
    const content = readFileSync(backupPath, 'utf-8');
    JSON.parse(content);
  } catch {
    return { success: false, error: 'Invalid JSON' };
  }

  writeFileSync(OPENCLAW_CONFIG_PATH, readFileSync(backupPath, 'utf-8'), 'utf-8');
  
  return { success: true };
}
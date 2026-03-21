export interface Provider {
  name: string;
  baseURL: string;
  apiKeyEnv: string;
  format: 'openai' | 'gemini';
  isFree: boolean;
}

export interface Model {
  id: string;
  name: string;
  provider: string;
  context_length?: number;
  pricing?: {
    prompt: string | number;
    completion: string | number;
  };
}

export interface ProviderAdapter {
  name: string;
  getModels(): Promise<Model[]>;
  chat(request: ChatRequest): Promise<Response>;
  validateKey(): Promise<boolean>;
}

export interface ChatRequest {
  model: string;
  messages: Array<{
    role: string;
    content: string;
  }>;
  max_tokens?: number;
  temperature?: number;
}

export interface ModelScore {
  model: Model;
  score: number;
  reasons: string[];
}

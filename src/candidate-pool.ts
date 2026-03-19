import { ENV, fetchWithTimeout } from './config';
import { fetchModels, filterFreeModels, rankModels, OpenRouterModel } from './models';

export interface CandidateModel {
  id: string;
  name: string;
  context_length?: number;
  lastValidated?: number;
  successCount?: number;
  failCount?: number;
}

export class CandidatePool {
  private candidates: Map<string, CandidateModel> = new Map();
  private failedModels: Map<string, number> = new Map();
  private lastUpdateTime: number | null = null;
  private validating = false;

  async validateModel(modelId: string): Promise<boolean> {
    try {
      const response = await fetchWithTimeout(
        `${ENV.OPENROUTER_BASE_URL}/chat/completions`,
        {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${ENV.OPENROUTER_API_KEY}`,
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({
            model: modelId,
            messages: [{ role: 'user', content: 'test' }],
            max_tokens: 1
          })
        },
        15000
      );

      if (response.status === 200) {
        return true;
      }
      return false;
    } catch {
      return false;
    }
  }

  async refresh(): Promise<void> {
    if (this.validating) {
      return;
    }

    this.validating = true;

    try {
      const models = await fetchModels();
      const freeModels = filterFreeModels(models);
      const ranked = rankModels(freeModels);

      this.candidates.clear();

      for (const { model } of ranked) {
        const isValid = await this.validateModel(model.id);
        
        if (isValid) {
          this.candidates.set(model.id, {
            id: model.id,
            name: model.name,
            context_length: model.context_length,
            lastValidated: Date.now(),
            successCount: 1,
            failCount: 0
          });
        }
      }

      this.lastUpdateTime = Date.now();
    } finally {
      this.validating = false;
    }
  }

  getCandidates(): CandidateModel[] {
    return Array.from(this.candidates.values())
      .filter(c => !this.failedModels.has(c.id));
  }

  markModelFailed(modelId: string): void {
    const current = this.failedModels.get(modelId) || 0;
    this.failedModels.set(modelId, current + 1);
    
    this.candidates.delete(modelId);
  }

  addCandidate(model: CandidateModel): void {
    if (!this.candidates.has(model.id)) {
      this.candidates.set(model.id, {
        ...model,
        successCount: 1,
        failCount: 0
      });
    }
  }

  clear(): void {
    this.candidates.clear();
    this.failedModels.clear();
    this.lastUpdateTime = null;
  }

  getLastUpdateTime(): number | null {
    return this.lastUpdateTime;
  }
}
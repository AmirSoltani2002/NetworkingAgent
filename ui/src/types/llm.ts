export type Thinking = 'instant' | 'medium' | 'high';

export interface LlmConfiguration {
  provider: 'openai';
  hasApiKey: boolean;
  maskedApiKey: string | null;
  model: string | null;
  thinking: Thinking;
}

export interface LlmModels {
  provider: 'openai';
  models: string[];
  fetchedAt: string;
}

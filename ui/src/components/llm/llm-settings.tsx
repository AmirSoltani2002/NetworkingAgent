import { useEffect, useState, type FormEvent } from 'react';
import { Button } from '@/components/ui/button';
import { Icon } from '@/components/chat/icon';
import { llmApi } from '@/lib/api';
import type { LlmConfiguration, Thinking } from '@/types/llm';

export function LlmSettings() {
  const [open, setOpen] = useState(true);
  const [configuration, setConfiguration] = useState<LlmConfiguration | null>(null);
  const [key, setKey] = useState('');
  const [models, setModels] = useState<string[]>([]);
  const [model, setModel] = useState('');
  const [thinking, setThinking] = useState<Thinking>('medium');
  const [loading, setLoading] = useState(true);
  const [modelsLoading, setModelsLoading] = useState(false);
  const [saving, setSaving] = useState<'key' | 'settings' | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    async function load() {
      try {
        const current = await llmApi.get(controller.signal);
        if (controller.signal.aborted) return;
        setConfiguration(current);
        setModel(current.model ?? '');
        setThinking(current.thinking);
        setLoading(false);
        if (current.hasApiKey) {
          setModelsLoading(true);
          const available = await llmApi.models(controller.signal);
          if (!controller.signal.aborted) setModels(available.models);
        }
      } catch (error) {
        if (!controller.signal.aborted) setError(error instanceof Error ? error.message : 'Could not load LLM settings.');
      } finally {
        if (!controller.signal.aborted) { setLoading(false); setModelsLoading(false); }
      }
    }
    void load();
    return () => controller.abort();
  }, []);

  async function refreshModels() {
    setModelsLoading(true);
    setError(null);
    try {
      const available = await llmApi.models();
      setModels(available.models);
      if (!available.models.length) setError('No models are available to this API key.');
    } catch (error) {
      setModels([]);
      setError(error instanceof Error ? error.message : 'Could not load models.');
    } finally {
      setModelsLoading(false);
    }
  }

  async function saveKey(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (saving || loading || modelsLoading) return;
    const apiKey = key;
    setKey('');
    setSaving('key');
    setError(null);
    setNotice(null);
    try {
      const current = await llmApi.save({ provider: 'openai', apiKey });
      setConfiguration(current);
      setModel(current.model ?? '');
      setModels([]);
      setNotice('API key saved.');
      await refreshModels();
    } catch (error) {
      setError(error instanceof Error ? error.message : 'Could not save the API key.');
    } finally {
      setSaving(null);
    }
  }

  async function saveSettings(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (saving || !models.includes(model)) return;
    setSaving('settings');
    setError(null);
    setNotice(null);
    try {
      const current = await llmApi.save({ provider: 'openai', model, thinking });
      setConfiguration(current);
      setNotice('Model settings saved.');
    } catch (error) {
      setError(error instanceof Error ? error.message : 'Could not save model settings.');
    } finally {
      setSaving(null);
    }
  }

  const busy = Boolean(saving || loading || modelsLoading);
  const dirty = model !== (configuration?.model ?? '') || thinking !== configuration?.thinking;
  return (
    <section className="llm-section" aria-label="LLM configuration">
      <h2 className="chat-section-title">
        <Button variant="ghost" className="chat-section-toggle" aria-expanded={open}
          aria-controls="llm-settings" onClick={() => setOpen(value => !value)}>
          <span>LLM</span><Icon name="chevron" />
        </Button>
      </h2>
      <div id="llm-settings" className="llm-settings" hidden={!open}>
        <label className="llm-field" htmlFor="llm-company">Company
          <select id="llm-company" value="openai" disabled={busy} onChange={() => undefined}>
            <option value="openai">OpenAI</option>
          </select>
        </label>
        <form onSubmit={event => void saveKey(event)} className="llm-form">
          <label className="llm-field" htmlFor="llm-api-key">API key
            <input id="llm-api-key" type="password" value={key} onChange={event => { setKey(event.target.value); setNotice(null); }}
              placeholder={configuration?.hasApiKey ? 'Enter a replacement key' : 'Enter your API key'}
              autoComplete="off" autoCapitalize="none" spellCheck={false} required minLength={12} maxLength={512}
              pattern="[A-Za-z0-9_-]{12,512}" disabled={busy} aria-describedby={configuration?.hasApiKey ? 'llm-saved-key' : undefined} />
          </label>
          {configuration?.hasApiKey && <p id="llm-saved-key" className="llm-saved-key"><span>Saved key</span><code>{configuration.maskedApiKey}</code></p>}
          <Button type="submit" variant="secondary" className="llm-action" disabled={busy || key.length < 12}>
            {saving === 'key' ? 'Saving…' : 'Save API key'}
          </Button>
        </form>
        <form onSubmit={event => void saveSettings(event)} className="llm-form llm-model-form">
          <div className="llm-model-heading">
            <label htmlFor="llm-model">Model</label>
            <Button type="button" variant="ghost" className="llm-refresh" disabled={busy || !configuration?.hasApiKey}
              onClick={() => void refreshModels()}>Refresh</Button>
          </div>
          <select id="llm-model" value={model} onChange={event => { setModel(event.target.value); setNotice(null); }}
            disabled={busy || !models.length}>
            <option value="">{modelsLoading ? 'Loading models…' : configuration?.hasApiKey ? 'Choose a model' : 'Save an API key first'}</option>
            {model && !models.includes(model) && <option value={model}>{model}</option>}
            {models.map(id => <option key={id} value={id}>{id}</option>)}
          </select>
          <label className="llm-field" htmlFor="llm-thinking">Thinking
            <select id="llm-thinking" value={thinking} onChange={event => { setThinking(event.target.value as Thinking); setNotice(null); }} disabled={busy}>
              <option value="instant">Instant</option><option value="medium">Medium</option><option value="high">High</option>
            </select>
          </label>
          <p className="llm-help">Thinking support depends on the model.</p>
          <Button type="submit" variant="secondary" className="llm-action" disabled={busy || !models.includes(model) || !dirty}>
            {saving === 'settings' ? 'Saving…' : 'Save settings'}
          </Button>
        </form>
        {loading && <p className="llm-help" role="status">Loading settings…</p>}
        {notice && <p className="llm-notice" role="status">{notice}</p>}
        {error && <p className="llm-error" role="alert">{error}</p>}
      </div>
    </section>
  );
}

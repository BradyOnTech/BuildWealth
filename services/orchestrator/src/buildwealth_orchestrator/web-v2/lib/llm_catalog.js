// Client-side LLM catalog (mirrors services/llm_model_catalog.py).
// Used by Settings and as a Copilot fallback when GET /api/copilot/llm-options
// is unavailable (e.g. container not rebuilt yet).

export const PROVIDERS = [
  { value: 'codex_subscription',        label: 'ChatGPT subscription',          hint: 'Codex · no API key' },
  { value: 'openai',                   label: 'OpenAI',                       hint: 'gpt-5.5 · default' },
  { value: 'anthropic',                label: 'Anthropic',                    hint: 'Claude family' },
  { value: 'gemini',                   label: 'Google Gemini',                hint: 'gemini-3.1' },
  { value: 'xai',                      label: 'xAI',                          hint: 'Grok 4.x' },
  { value: 'openrouter',               label: 'OpenRouter',                   hint: 'Many models · one key · cheap' },
  { value: 'custom_openai_compatible', label: 'Custom (OpenAI-compatible)',   hint: 'Self-hosted, proxies' },
];

export const PROVIDER_DEFAULTS = {
  codex_subscription:         { llm_model: 'codex-recommended',    llm_base_url: '' },
  openai:                   { llm_model: 'gpt-5.5',               llm_base_url: 'https://api.openai.com/v1' },
  anthropic:                { llm_model: 'claude-opus-4-8',       llm_base_url: 'https://api.anthropic.com/v1' },
  gemini:                   { llm_model: 'gemini-3.1-flash-lite', llm_base_url: 'https://generativelanguage.googleapis.com/v1beta/openai' },
  xai:                      { llm_model: 'grok-4.5',              llm_base_url: 'https://api.x.ai/v1' },
  openrouter:               { llm_model: 'openrouter/auto',       llm_base_url: 'https://openrouter.ai/api/v1' },
  custom_openai_compatible: { llm_model: '',                      llm_base_url: '' },
};

/** @type {Record<string, Array<{id:string,label:string,cost:string,blurb?:string,recommended?:boolean,cheap?:boolean,price?:string}>>} */
export const PROVIDER_MODELS = {
  codex_subscription: [
    { id: 'codex-recommended', label: 'Codex recommended', cost: 'plan', blurb: 'Uses the best compatible model for the installed Codex runtime', recommended: true },
  ],
  xai: [
    { id: 'grok-4.5', label: 'Grok 4.5', cost: '$$$', blurb: 'Flagship · tools & reasoning', recommended: true, price: '$2 / $6' },
    { id: 'grok-4.3', label: 'Grok 4.3', cost: '$$', blurb: 'Strong general chat', price: '$1.25 / $2.50' },
    { id: 'grok-4.20-0309-reasoning', label: 'Grok 4.20 Reasoning', cost: '$$', blurb: 'Deeper multi-step reasoning', price: '$1.25 / $2.50' },
    { id: 'grok-4.20-0309-non-reasoning', label: 'Grok 4.20 Fast', cost: '$$', blurb: 'Faster responses', price: '$1.25 / $2.50', cheap: true },
    { id: 'grok-4.20-multi-agent-0309', label: 'Grok 4.20 Multi-agent', cost: '$$', blurb: 'Built-in multi-agent', price: '$1.25 / $2.50' },
  ],
  openai: [
    { id: 'gpt-5.5', label: 'GPT-5.5', cost: '$$$', blurb: 'Latest flagship', recommended: true },
    { id: 'gpt-5-mini', label: 'GPT-5 mini', cost: '$$', blurb: 'Cheaper everyday chat', cheap: true },
    { id: 'gpt-4.1', label: 'GPT-4.1', cost: '$$$', blurb: 'Stable tools-capable' },
    { id: 'gpt-4.1-mini', label: 'GPT-4.1 mini', cost: '$$', blurb: 'Fast / lower cost', cheap: true },
    { id: 'gpt-4o-mini', label: 'GPT-4o mini', cost: '$', blurb: 'Very cheap tools model', cheap: true, price: '~$0.15 / $0.60' },
  ],
  anthropic: [
    { id: 'claude-opus-4-8', label: 'Claude Opus 4.8', cost: '$$$$', blurb: 'Highest capability', recommended: true },
    { id: 'claude-opus-4-7', label: 'Claude Opus 4.7', cost: '$$$$', blurb: 'Previous Opus generation' },
    { id: 'claude-sonnet-4-5', label: 'Claude Sonnet 4.5', cost: '$$$', blurb: 'Balanced quality & cost' },
    { id: 'claude-haiku-4-5', label: 'Claude Haiku 4.5', cost: '$', blurb: 'Fast / economical', cheap: true },
  ],
  gemini: [
    { id: 'gemini-3.1-flash-lite', label: 'Gemini 3.1 Flash Lite', cost: '$', blurb: 'Fast & cheap', recommended: true, cheap: true },
    { id: 'gemini-3.1-flash', label: 'Gemini 3.1 Flash', cost: '$$', blurb: 'Balanced', cheap: true },
    { id: 'gemini-3.1-pro', label: 'Gemini 3.1 Pro', cost: '$$$', blurb: 'Higher quality' },
  ],
  openrouter: [
    { id: 'openrouter/auto', label: 'OpenRouter Auto', cost: '$', blurb: 'Router picks a capable cheap model', recommended: true, cheap: true },
    { id: 'deepseek/deepseek-chat', label: 'DeepSeek Chat', cost: '$', blurb: 'Strong & very cheap', cheap: true, price: 'Often well under $1 / 1M' },
    { id: 'google/gemini-2.0-flash-001', label: 'Gemini 2.0 Flash', cost: '$', blurb: 'Fast via OpenRouter', cheap: true },
    { id: 'meta-llama/llama-3.3-70b-instruct', label: 'Llama 3.3 70B', cost: '$', blurb: 'Open weights · low cost', cheap: true },
    { id: 'qwen/qwen-2.5-72b-instruct', label: 'Qwen 2.5 72B', cost: '$', blurb: 'Capable open model', cheap: true },
    { id: 'mistralai/mistral-small-3.1-24b-instruct', label: 'Mistral Small', cost: '$', blurb: 'Economical tools chat', cheap: true },
    { id: 'openai/gpt-4o-mini', label: 'GPT-4o mini (via OR)', cost: '$', blurb: 'Cheap OpenAI-class tools', cheap: true },
    { id: 'anthropic/claude-3.5-haiku', label: 'Claude Haiku (via OR)', cost: '$$', blurb: 'Fast Claude-class', cheap: true },
    { id: 'x-ai/grok-3-mini', label: 'Grok mini (via OR)', cost: '$$', blurb: 'When available on OpenRouter', cheap: true },
  ],
  custom_openai_compatible: [],
};

function modelsForApi(providerId) {
  return (PROVIDER_MODELS[providerId] || []).map(m => ({
    id: m.id,
    label: m.label,
    cost_band: m.cost,
    blurb: m.blurb || '',
    recommended: !!m.recommended,
    cheap: !!m.cheap,
    price_hint: m.price || '',
    tools: true,
  }));
}

/**
 * Build a GET /api/copilot/llm-options-shaped payload from /api/settings.
 * Works with multi-vendor responses and with older single-key backends.
 */
export function buildLlmOptionsFromSettings(settings) {
  const s = settings && typeof settings === 'object' ? settings : {};
  const activeProvider = String(s.llm_provider || 'openai').trim().toLowerCase();
  const activeModel = String(s.llm_model || '').trim();
  const connectedList = Array.isArray(s.llm_connected_providers) ? s.llm_connected_providers : null;
  const keysMeta = s.llm_provider_keys_meta && typeof s.llm_provider_keys_meta === 'object'
    ? s.llm_provider_keys_meta
    : null;

  const connectedIds = new Set();
  if (connectedList) {
    for (const item of connectedList) {
      if (item?.connected && item.id) connectedIds.add(String(item.id).toLowerCase());
    }
  } else if (keysMeta) {
    for (const [pid, meta] of Object.entries(keysMeta)) {
      if (meta?.configured) connectedIds.add(String(pid).toLowerCase());
    }
  } else if (s.llm_api_key_configured || (String(s.llm_api_key || '').startsWith('•'))) {
    // Legacy single-key settings response.
    connectedIds.add(activeProvider);
    if (activeProvider === 'custom_openai_compatible' && s.llm_base_url) {
      connectedIds.add(activeProvider);
    }
  }

  if (activeProvider === 'custom_openai_compatible' && String(s.llm_base_url || '').trim()) {
    connectedIds.add(activeProvider);
  }

  const providers = PROVIDERS.map(p => {
    const id = p.value;
    const models = modelsForApi(id);
    const connected = connectedIds.has(id);
    return {
      id,
      label: p.label,
      hint: p.hint,
      default_model: PROVIDER_DEFAULTS[id]?.llm_model || '',
      default_base_url: PROVIDER_DEFAULTS[id]?.llm_base_url || '',
      auth_note: '',
      connected,
      is_active_default: id === activeProvider,
      models,
    };
  });

  const activeModels = modelsForApi(activeProvider);
  const match = activeModels.find(m => m.id === activeModel);
  const resolved = {
    provider: activeProvider,
    model: activeModel || PROVIDER_DEFAULTS[activeProvider]?.llm_model || '',
    label: match?.label || activeModel || 'Default',
    cost_band: match?.cost_band || '',
    source: 'workspace_default',
    cheap: !!match?.cheap,
  };

  return {
    catalog_version: 'client-fallback',
    active_provider: activeProvider,
    active_model: resolved.model,
    resolved,
    connected_providers: providers.filter(p => p.connected),
    providers,
  };
}

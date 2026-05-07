# LLM Providers

BuildWealth Copilot supports a small, quality-controlled provider set so client-side tool calling stays predictable.

## Supported Providers

| Provider | Adapter | Default model | Default base URL |
| --- | --- | --- | --- |
| OpenAI | OpenAI-compatible Chat Completions | `gpt-5.5` | `https://api.openai.com/v1` |
| Gemini | OpenAI-compatible Chat Completions | `gemini-3.1-flash-lite` | `https://generativelanguage.googleapis.com/v1beta/openai` |
| Anthropic | Native Messages API | `claude-opus-4-7` | `https://api.anthropic.com/v1` |
| xAI | Native Responses API | `grok-4.20-reasoning-latest` | `https://api.x.ai/v1` |
| Custom OpenAI-compatible | OpenAI-compatible Chat Completions | user supplied | user supplied |

OpenRouter is intentionally not listed. Its broad model catalog makes tool-call behavior too variable for a financial planning assistant.

## Runtime Settings

Use the Settings UI for local single-user configuration, or set environment variables:

```bash
LLM_PROVIDER=openai
LLM_API_KEY=
LLM_MODEL=gpt-5.5
LLM_BASE_URL=https://api.openai.com/v1
LLM_TIMEOUT_SECONDS=60
LLM_MAX_TOKENS=2048
LLM_PARALLEL_TOOL_CALLS=true
```

Legacy `OPENAI_API_KEY`, `OPENAI_MODEL`, and `OPENAI_BASE_URL` still work for OpenAI compatibility.

## Provider Test

The Settings page has a **Test Provider** button. It runs a real two-step tool loop:

1. Ask the model to call `echo_tool` with value `7`.
2. Execute that tool locally.
3. Return the tool result to the provider.
4. Verify the final answer contains `ECHO_VALUE=7`.

This tests the same adapter path Copilot uses for BuildWealth tools.

## Live Test Suite

The live provider tests are skipped unless provider keys are set:

```bash
OPENAI_API_KEY=... pytest services/orchestrator/tests/test_llm_provider_live.py -q
GEMINI_API_KEY=... pytest services/orchestrator/tests/test_llm_provider_live.py -q
ANTHROPIC_API_KEY=... pytest services/orchestrator/tests/test_llm_provider_live.py -q
XAI_API_KEY=... pytest services/orchestrator/tests/test_llm_provider_live.py -q
```

Optional model/base URL overrides follow the provider prefix:

```bash
GEMINI_MODEL=gemini-3.1-flash-lite
GEMINI_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai
```

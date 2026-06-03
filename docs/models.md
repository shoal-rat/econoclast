# Configuring models

Econoclast is provider-agnostic. The deterministic forensics need **nothing**. The LLM attacks need
one provider. Keys are read from the environment (a local `.env` works via `python-dotenv`).

## Pick a provider

| Provider | Env var | Notes |
|---|---|---|
| OpenAI | `OPENAI_API_KEY` | also any OpenAI-compatible endpoint via `base_url` |
| Anthropic | `ANTHROPIC_API_KEY` | default if present |
| Google Gemini | `GOOGLE_API_KEY` (or `GEMINI_API_KEY`) | |
| OpenRouter | `OPENROUTER_API_KEY` | one key, hundreds of models |
| Ollama / vLLM / LM Studio | none | local, OpenAI-compatible; set `base_url` |
| LiteLLM | provider's own | passthrough to 100+ providers |

With **no** config file, Econoclast auto-selects sensible defaults from whichever key is present, and
falls back to the offline **mock** model if none is.

Check what it sees:

```bash
econoclast models
```

## Configure routing

In `econoclast.yaml` (see [`econoclast.example.yaml`](../econoclast.example.yaml)):

```yaml
models:
  extractor: anthropic:claude-haiku-4-5-20251001
  attacker:
    - anthropic:claude-opus-4-8        # primary
    - openai:gpt-4o                    # fallback if the primary errors
  referee: anthropic:claude-opus-4-8
```

The three **roles**:

- `extractor` — cheap/fast model for light extraction work.
- `attacker` — the strong reasoning model that runs the adversarial critiques.
- `referee` — writes the final meta-review (can equal `attacker`).

## Local models (no key, no cloud)

```yaml
models:
  attacker: { provider: ollama, model: "llama3.1:70b" }
  referee:  { provider: ollama, model: "llama3.1:70b" }
```

Econoclast talks to Ollama's OpenAI-compatible endpoint at `http://localhost:11434/v1`. The JSON
attack protocol works even on models without native tool-calling. For best results use a 70B-class
model; small models miss subtle identification flaws.

## Custom OpenAI-compatible endpoints

```yaml
models:
  attacker: { provider: openai, model: "Qwen2.5-72B", base_url: "http://localhost:8000/v1" }
```

Works with vLLM, Together, Groq, Fireworks, DeepInfra, LM Studio, etc.

## LiteLLM passthrough

`pip install "econoclast[litellm]"`, then:

```yaml
models:
  attacker: { provider: litellm, model: "gemini/gemini-1.5-pro" }
```

LiteLLM handles the provider quirks; Econoclast just hands it the model string.

## Cost

Every run prints token usage and an estimated cost. Override the price table per model:

```yaml
pricing:
  "claude-opus-4-8": [15.0, 75.0]   # [input, output] USD per 1M tokens
```

A typical full review is ~8–14 LLM calls (one per LLM attack + the referee). Use `--no-llm` for the
free, offline forensic pass, or route `attacker` to a cheap/local model.

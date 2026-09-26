AZRAS Planning PATCH 588

Policy change
- Do not retain old responses from the same AI provider.
- Keep only one current response per actual provider.

Canonical provider IDs
- chatgpt
- claude
- gemini
- meta
- grok
- copilot
- perplexity

Legacy alias migration
- ChatGPT + chatgpt -> chatgpt
- Claude (Anthropic) + claude -> claude
- Meta AI - Muse Spark 1.1 + meta -> meta
- Gemini + gemini -> gemini

Replacement rule
- Re-import from the same provider replaces the previous current response.
- Provider count does not increase.
- If legacy duplicate aliases already exist, keep only the newest imported snapshot.
- Old same-provider responses are discarded from active Project JSON.

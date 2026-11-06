# Persona Cloner

A modern Flask web application that converts raw WhatsApp chat exports (`.txt`) into psychologically grounded LLM personas, production-ready system prompts, and SillyTavern character cards.

---

## 3-Flow Workflow

1. **Configuration**:
   - Multi-provider support (OpenRouter, OpenAI, Fireworks AI, and custom OpenAI-compatible endpoints like Ollama or LocalAI).
   - Pre-configured models (DeepSeek v4.1, Claude 3.7, GPT-4o, Gemini 2.0 Flash) + custom model IDs.
   - Quick "Test Connection" button.
   - Credential persistence via browser `localStorage` (client-side only).

2. **Upload & Target Selection**:
   - Drag-and-drop or file upload for WhatsApp `.txt` exports (supports both iOS and Android export formats).
   - Instant parsing with participant breakdown (message count, percentage, media count, date range).
   - Target sender selection and character customization (Character Name and user aliases).
   - Real-time step-by-step progress tracker during cloning.

3. **Output & Live Test Chat**:
   - Visual Big Five trait score cards and personality summaries.
   - Ready-to-use system prompt viewer with one-click copy.
   - One-click downloads:
     - `system_prompt.txt`
     - `character_card.json` (SillyTavern V2 format)
     - `persona_profile.json`
     - `stylometry.json`
   - Interactive WhatsApp-style live test chat window to talk directly with the cloned persona.

---

## Getting Started

### Requirements
- Python >= 3.12
- [uv](https://docs.astral.sh/uv/)

### Installation

```bash
uv sync
```

### Run the Web Server

```bash
uv run python main.py
```

Open [http://127.0.0.1:5000](http://127.0.0.1:5000) in your browser.

---

## Running Tests

Run the complete test suite:

```bash
uv run python -m unittest discover tests
```

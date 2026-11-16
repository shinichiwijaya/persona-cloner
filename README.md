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

---

## End-to-End Testing & Walkthrough (Ubuntu Dialogue Corpus)

This walkthrough shows how to test **Persona Cloner** from scratch using the **Ubuntu Dialogue Corpus** from Kaggle—from downloading and converting the dataset into a clean 2-user WhatsApp chat export, to installing dependencies with `uv`, cloning a persona, and chatting with the bot.

### Prerequisites

- [uv](https://docs.astral.sh/uv/) installed (`uv --version`)

### 1. Install Project Dependencies

From the project root:
```bash
uv sync
```

### 2. Download the Test Dataset from Kaggle

1. Go to [https://www.kaggle.com/datasets/rtatman/ubuntu-dialogue-corpus/](https://www.kaggle.com/datasets/rtatman/ubuntu-dialogue-corpus/).
2. Click **Download** (requires a free Kaggle account), or use the Kaggle CLI:
   ```bash
   kaggle datasets download -d rtatman/ubuntu-dialogue-corpus
   ```
3. Unzip the archive and place `dialogueText.csv` in the project root (`persona-cloner/dialogueText.csv`).

### 3. Extract a Clean 2-User WhatsApp Chat (`whatsapp_chat.txt`)

Run `convert_to_whatsapp.py` to convert `dialogueText.csv` into a ~2,000-message, profanity-free, 2-user WhatsApp `.txt` export:

```bash
python3 convert_to_whatsapp.py
```

By default, this picks the most active profanity-free user (`bazhang`), selects 667 clean 2-user back-and-forth dialogues (~2,000 messages total), maps the other speaker to `User`, filters out any dialogue containing curse words, and writes `whatsapp_chat.txt` in iOS WhatsApp format (`[DD/MM/YYYY, HH:MM:SS] Sender: text`).

Optional flags:
```bash
# Use a different profanity-free user (e.g., Dr_Willis, Jack_Sparrow, soundray)
python3 convert_to_whatsapp.py -u Dr_Willis

# Customize partner name, message limit, or Android format
python3 convert_to_whatsapp.py -p Partner -n 2000 -f android -o whatsapp_chat.txt
```

### 4. Start the Web Application

```bash
uv run python main.py
```

Open [http://127.0.0.1:5000](http://127.0.0.1:5000) in your browser.

### 5. Walkthrough: Clone the Persona & Chat with the Bot

1. **Tab 1 — Configuration**:
   - Choose your **LLM Provider** (OpenRouter, OpenAI, Fireworks AI, or a custom OpenAI-compatible endpoint like Ollama/LocalAI).
   - Enter your **API Key** and select (or enter) a **Model ID**.
   - Click **Test Connection** to verify your credentials.
2. **Tab 2 — Upload & Target**:
   - Drag and drop `whatsapp_chat.txt` (or click to browse and upload it).
   - Confirm the participant breakdown shows **2 users** (`bazhang` and `User`) totaling ~2,000 messages.
   - Select **`bazhang`** (or whichever target user you extracted) as the **Target Sender**, and optionally customize the **Character Name** and aliases.
   - Click **Start Persona Cloning** and wait for all 4 pipeline steps to finish.
3. **Tab 3 — Output & Live Chat**:
   - Review the generated Big Five trait scores, personality summary, and system prompt (or download `system_prompt.txt`, `character_card.json`, `persona_profile.json`, and `stylometry.json`).
   - Use the **Live Chat** panel on the right to send messages and talk directly with the cloned persona!

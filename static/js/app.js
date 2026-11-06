document.addEventListener("DOMContentLoaded", () => {
  // App state
  const state = {
    provider: localStorage.getItem("pc_provider") || "openrouter",
    apiKey: localStorage.getItem("pc_api_key") || "",
    model: localStorage.getItem("pc_model") || "deepseek/deepseek-v4.1-flash",
    baseUrl: localStorage.getItem("pc_base_url") || "",
    chatText: "",
    selectedTarget: "",
    charName: "",
    userAliases: "",
    generatedResult: null,
    chatHistory: [],
  };

  // Elements
  const tabBtns = document.querySelectorAll(".tab-btn");
  const tabContents = document.querySelectorAll(".tab-content");

  // Config elements
  const providerSelect = document.getElementById("provider-select");
  const apiKeyInput = document.getElementById("api-key-input");
  const modelSelect = document.getElementById("model-select");
  const customModelInput = document.getElementById("custom-model-input");
  const baseUrlGroup = document.getElementById("base-url-group");
  const baseUrlInput = document.getElementById("base-url-input");
  const testConnBtn = document.getElementById("btn-test-connection");
  const connAlert = document.getElementById("connection-alert");

  // Upload elements
  const dropzone = document.getElementById("dropzone");
  const fileInput = document.getElementById("file-input");
  const uploadAlert = document.getElementById("upload-alert");
  const participantsCard = document.getElementById("participants-card");
  const participantsTableBody = document.querySelector("#participants-table tbody");
  const charNameInput = document.getElementById("char-name-input");
  const userAliasesInput = document.getElementById("user-aliases-input");
  const generateBtn = document.getElementById("btn-generate-persona");
  const progressCard = document.getElementById("progress-card");
  const progressSteps = document.getElementById("progress-steps");

  // Output elements
  const outputPlaceholder = document.getElementById("output-placeholder");
  const outputContent = document.getElementById("output-content");
  const personaHeaderTitle = document.getElementById("persona-header-title");
  const personaSummaryText = document.getElementById("persona-summary-text");
  const traitsGrid = document.getElementById("traits-grid");
  const systemPromptViewer = document.getElementById("system-prompt-viewer");
  const copyPromptBtn = document.getElementById("btn-copy-prompt");

  // Download buttons
  const btnDlPrompt = document.getElementById("btn-dl-prompt");
  const btnDlCard = document.getElementById("btn-dl-card");
  const btnDlProfile = document.getElementById("btn-dl-profile");

  // Chat elements
  const chatMessages = document.getElementById("chat-messages");
  const chatInput = document.getElementById("chat-input");
  const chatSendBtn = document.getElementById("chat-send-btn");
  const chatClearBtn = document.getElementById("chat-clear-btn");
  const chatAvatar = document.getElementById("chat-avatar");
  const chatCharName = document.getElementById("chat-char-name");

  // 1. Initialize & Tab Management
  function switchTab(tabId) {
    tabBtns.forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.tab === tabId);
    });
    tabContents.forEach((content) => {
      content.classList.toggle("active", content.id === tabId);
    });
  }

  tabBtns.forEach((btn) => {
    btn.addEventListener("click", () => switchTab(btn.dataset.tab));
  });

  // 2. Load Stored Configuration
  providerSelect.value = state.provider;
  apiKeyInput.value = state.apiKey;
  baseUrlInput.value = state.baseUrl;

  function updateProviderUI() {
    state.provider = providerSelect.value;
    localStorage.setItem("pc_provider", state.provider);

    baseUrlGroup.style.display = state.provider === "custom" ? "block" : "none";
    loadModelsForProvider(state.provider);
  }

  async function loadModelsForProvider(provider) {
    try {
      const res = await fetch("/api/default-models");
      const modelsData = await res.json();
      const list = modelsData[provider] || [];

      modelSelect.innerHTML = "";
      list.forEach((m) => {
        const opt = document.createElement("option");
        opt.value = m.id;
        opt.textContent = m.name;
        modelSelect.appendChild(opt);
      });

      const customOpt = document.createElement("option");
      customOpt.value = "CUSTOM";
      customOpt.textContent = "— Custom Model ID —";
      modelSelect.appendChild(customOpt);

      if (state.model && [...modelSelect.options].some((o) => o.value === state.model)) {
        modelSelect.value = state.model;
        customModelInput.style.display = "none";
      } else if (state.model) {
        modelSelect.value = "CUSTOM";
        customModelInput.value = state.model;
        customModelInput.style.display = "block";
      }
    } catch (e) {
      console.error("Could not fetch models:", e);
    }
  }

  providerSelect.addEventListener("change", updateProviderUI);

  modelSelect.addEventListener("change", () => {
    if (modelSelect.value === "CUSTOM") {
      customModelInput.style.display = "block";
      state.model = customModelInput.value;
    } else {
      customModelInput.style.display = "none";
      state.model = modelSelect.value;
    }
    localStorage.setItem("pc_model", state.model);
  });

  customModelInput.addEventListener("input", () => {
    state.model = customModelInput.value.trim();
    localStorage.setItem("pc_model", state.model);
  });

  apiKeyInput.addEventListener("input", () => {
    state.apiKey = apiKeyInput.value.trim();
    localStorage.setItem("pc_api_key", state.apiKey);
  });

  baseUrlInput.addEventListener("input", () => {
    state.baseUrl = baseUrlInput.value.trim();
    localStorage.setItem("pc_base_url", state.baseUrl);
  });

  updateProviderUI();

  // Test Connection
  testConnBtn.addEventListener("click", async () => {
    connAlert.style.display = "none";
    testConnBtn.disabled = true;
    testConnBtn.textContent = "Testing...";

    try {
      const res = await fetch("/api/test-connection", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          provider: state.provider,
          api_key: state.apiKey,
          model: state.model,
          base_url: state.baseUrl,
        }),
      });
      const data = await res.json();
      connAlert.style.display = "flex";
      if (data.success) {
        connAlert.className = "alert alert-success";
        connAlert.textContent = data.message;
      } else {
        connAlert.className = "alert alert-danger";
        connAlert.textContent = data.message || "Connection failed.";
      }
    } catch (err) {
      connAlert.style.display = "flex";
      connAlert.className = "alert alert-danger";
      connAlert.textContent = err.message || "Failed to reach server.";
    } finally {
      testConnBtn.disabled = false;
      testConnBtn.textContent = "Test Connection";
    }
  });

  // 3. File Upload & Parsing
  dropzone.addEventListener("click", () => fileInput.click());

  dropzone.addEventListener("dragover", (e) => {
    e.preventDefault();
    dropzone.classList.add("dragover");
  });

  dropzone.addEventListener("dragleave", () => {
    dropzone.classList.remove("dragover");
  });

  dropzone.addEventListener("drop", (e) => {
    e.preventDefault();
    dropzone.classList.remove("dragover");
    if (e.dataTransfer.files.length > 0) {
      handleChatFile(e.dataTransfer.files[0]);
    }
  });

  fileInput.addEventListener("change", (e) => {
    if (e.target.files.length > 0) {
      handleChatFile(e.target.files[0]);
    }
  });

  async function handleChatFile(file) {
    uploadAlert.style.display = "none";
    const text = await file.text();
    state.chatText = text;

    const formData = new FormData();
    formData.append("file", file);

    try {
      const res = await fetch("/api/parse-chat", {
        method: "POST",
        body: formData,
      });
      const data = await res.json();

      if (!data.success) {
        throw new Error(data.error || "Failed to parse chat file.");
      }

      displayParticipants(data.participants, data.total_messages, data.date_range);
    } catch (err) {
      uploadAlert.style.display = "flex";
      uploadAlert.className = "alert alert-danger";
      uploadAlert.textContent = err.message;
    }
  }

  function displayParticipants(participants, totalMessages, dateRange) {
    participantsTableBody.innerHTML = "";
    participantsCard.style.display = "block";

    participants.forEach((p, idx) => {
      const row = document.createElement("tr");

      const tdRadio = document.createElement("td");
      const radio = document.createElement("input");
      radio.type = "radio";
      radio.name = "target_participant";
      radio.value = p.name;
      if (idx === 0) {
        radio.checked = true;
        state.selectedTarget = p.name;
        charNameInput.value = p.name;
      }
      radio.addEventListener("change", () => {
        state.selectedTarget = p.name;
        charNameInput.value = p.name;
      });
      tdRadio.appendChild(radio);

      const tdName = document.createElement("td");
      tdName.innerHTML = `<strong>${escapeHtml(p.name)}</strong>`;

      const tdCount = document.createElement("td");
      tdCount.textContent = `${p.count.toLocaleString()} (${p.percentage}%)`;

      const tdMedia = document.createElement("td");
      tdMedia.textContent = p.media_count.toLocaleString();

      const tdDate = document.createElement("td");
      tdDate.textContent = `${p.first_message} to ${p.last_message}`;

      row.appendChild(tdRadio);
      row.appendChild(tdName);
      row.appendChild(tdCount);
      row.appendChild(tdMedia);
      row.appendChild(tdDate);

      participantsTableBody.appendChild(row);
    });

    uploadAlert.style.display = "flex";
    uploadAlert.className = "alert alert-success";
    uploadAlert.textContent = `Successfully parsed ${totalMessages.toLocaleString()} messages from ${participants.length} participants (${dateRange[0]} - ${dateRange[1]}).`;
  }

  // 4. Generate Persona (Streaming SSE / Read stream)
  generateBtn.addEventListener("click", async () => {
    if (!state.chatText) {
      alert("Please upload a WhatsApp chat file first.");
      return;
    }
    if (!state.selectedTarget) {
      alert("Please select a target participant to clone.");
      return;
    }
    if (!state.apiKey && state.provider !== "custom") {
      alert("Please set your API Key in the Configuration tab.");
      switchTab("tab-config");
      return;
    }

    generateBtn.disabled = true;
    generateBtn.textContent = "Cloning Persona...";
    progressCard.style.display = "block";

    // Reset steps UI
    const stepItems = document.querySelectorAll(".step-item");
    stepItems.forEach((item) => {
      item.className = "step-item pending";
      item.querySelector(".step-icon").textContent = "○";
    });

    const payload = {
      chat_text: state.chatText,
      target_name: state.selectedTarget,
      char_name: charNameInput.value.trim() || state.selectedTarget,
      user_aliases: userAliasesInput.value.split(",").map((s) => s.trim()).filter(Boolean),
      provider: state.provider,
      api_key: state.apiKey,
      model: state.model,
      base_url: state.baseUrl,
    };

    try {
      const response = await fetch("/api/generate-persona", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      const reader = response.body.getReader();
      const decoder = new TextDecoder("utf-8");
      let buffer = "";

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n\n");
        buffer = lines.pop();

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const jsonStr = line.slice(6).trim();
          try {
            const event = JSON.parse(jsonStr);
            handleProgressEvent(event);
          } catch (e) {
            console.error("JSON parse error:", e, jsonStr);
          }
        }
      }
    } catch (err) {
      alert("Generation failed: " + err.message);
    } finally {
      generateBtn.disabled = false;
      generateBtn.textContent = "Start Persona Cloning";
    }
  });

  function handleProgressEvent(event) {
    if (event.status === "error") {
      alert("Error during cloning: " + event.error);
      return;
    }

    const stepEl = document.querySelector(`.step-item[data-step="${event.step}"]`);
    if (stepEl) {
      if (event.status === "running") {
        stepEl.className = "step-item running";
        stepEl.querySelector(".step-icon").textContent = "⏳";
      } else if (event.status === "completed") {
        stepEl.className = "step-item completed";
        stepEl.querySelector(".step-icon").textContent = "✓";
      }
    }

    if (event.result) {
      state.generatedResult = event.result;
      renderOutput(event.result);
      switchTab("tab-output");
    }
  }

  // 5. Render Output & Persona Visualization
  function renderOutput(result) {
    outputPlaceholder.style.display = "none";
    outputContent.style.display = "block";

    personaHeaderTitle.textContent = `${result.char_name} (${result.target_name})`;
    personaSummaryText.textContent = result.profile.ringkasan_kepribadian || "Persona generated.";

    // Traits Grid
    traitsGrid.innerHTML = "";
    const bigFive = result.profile.big_five || {};
    const traitNames = {
      openness: "Openness",
      conscientiousness: "Conscientiousness",
      extraversion: "Extraversion",
      agreeableness: "Agreeableness",
      neuroticism: "Neuroticism",
    };

    for (const [key, label] of Object.entries(traitNames)) {
      const data = bigFive[key] || { skor: 50 };
      const score = data.skor;

      const card = document.createElement("div");
      card.className = "trait-card";
      card.innerHTML = `
        <div class="trait-name">${label}</div>
        <div class="trait-score">${score}<span style="font-size:0.8rem;font-weight:400;color:var(--text-muted)">/100</span></div>
        <div class="trait-bar-bg">
          <div class="trait-bar-fill" style="width: ${score}%"></div>
        </div>
      `;
      traitsGrid.appendChild(card);
    }

    // System prompt viewer
    systemPromptViewer.textContent = result.system_prompt;

    // Chat header info
    chatCharName.textContent = result.char_name;
    chatAvatar.textContent = (result.char_name || "P")[0].toUpperCase();

    // Reset live chat
    state.chatHistory = [];
    chatMessages.innerHTML = `
      <div class="message-bubble char">
        ${escapeHtml(result.stats.pembuka_teratas?.[0]?.[0] || "halo!")}
      </div>
    `;
  }

  // Copy System Prompt
  copyPromptBtn.addEventListener("click", () => {
    if (!state.generatedResult) return;
    navigator.clipboard.writeText(state.generatedResult.system_prompt).then(() => {
      copyPromptBtn.textContent = "Copied!";
      setTimeout(() => {
        copyPromptBtn.textContent = "Copy Prompt";
      }, 2000);
    });
  });

  // Downloads
  btnDlPrompt.addEventListener("click", () => {
    window.location.href = "/api/download/system-prompt";
  });
  btnDlCard.addEventListener("click", () => {
    window.location.href = "/api/download/character-card";
  });
  btnDlProfile.addEventListener("click", () => {
    window.location.href = "/api/download/profile";
  });

  // 6. Live Test Chat
  async function sendChatMessage() {
    const text = chatInput.value.trim();
    if (!text || !state.generatedResult) return;

    chatInput.value = "";
    appendChatMessage("user", text);
    state.chatHistory.push({ sender: "user", text });

    // Show typing bubble
    const typingBubble = document.createElement("div");
    typingBubble.className = "message-bubble char";
    typingBubble.id = "typing-bubble";
    typingBubble.textContent = "typing...";
    chatMessages.appendChild(typingBubble);
    chatMessages.scrollTop = chatMessages.scrollHeight;

    chatSendBtn.disabled = true;

    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: text,
          history: state.chatHistory.slice(-10),
          system_prompt: state.generatedResult.system_prompt,
          char_name: state.generatedResult.char_name,
          user_name: "You",
          provider: state.provider,
          api_key: state.apiKey,
          model: state.model,
          base_url: state.baseUrl,
        }),
      });

      const data = await res.json();
      const typingEl = document.getElementById("typing-bubble");
      if (typingEl) typingEl.remove();

      if (data.success) {
        appendChatMessage("char", data.reply);
        state.chatHistory.push({ sender: "char", text: data.reply });
      } else {
        appendChatMessage("char", `[Error: ${data.error}]`);
      }
    } catch (e) {
      const typingEl = document.getElementById("typing-bubble");
      if (typingEl) typingEl.remove();
      appendChatMessage("char", `[Connection Error: ${e.message}]`);
    } finally {
      chatSendBtn.disabled = false;
      chatInput.focus();
    }
  }

  function appendChatMessage(sender, text) {
    const bubble = document.createElement("div");
    bubble.className = `message-bubble ${sender}`;
    bubble.textContent = text;
    chatMessages.appendChild(bubble);
    chatMessages.scrollTop = chatMessages.scrollHeight;
  }

  chatSendBtn.addEventListener("click", sendChatMessage);
  chatInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      sendChatMessage();
    }
  });

  chatClearBtn.addEventListener("click", () => {
    state.chatHistory = [];
    chatMessages.innerHTML = `
      <div class="message-bubble char">
        ${escapeHtml(state.generatedResult?.stats?.pembuka_teratas?.[0]?.[0] || "halo!")}
      </div>
    `;
  });

  function escapeHtml(str) {
    if (!str) return "";
    return str
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }
});

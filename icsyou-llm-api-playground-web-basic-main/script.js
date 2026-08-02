"use strict";

const DEFAULT_SYSTEM_PROMPT =
  "คุณคือผู้ช่วยคิดโครงงาน AI สำหรับนักเรียนมัธยมปลาย ตอบเป็นภาษาไทยที่เข้าใจง่าย";
const SAMPLE_SYSTEM_PROMPT =
  "คุณคือครูที่ปรึกษาโครงงาน AI สำหรับนักเรียนมัธยมปลาย อธิบายทีละขั้น ใช้คำง่าย ยกตัวอย่างใกล้ตัว และจบด้วยคำถามหนึ่งข้อเพื่อชวนคิดต่อ";

const $ = (selector) => document.querySelector(selector);
const elements = {
  learningMode: $("#learning-mode"),
  learningPanel: $("#learning-panel"),
  providerStatus: $("#provider-status"),
  activeModel: $("#active-model"),
  systemPrompt: $("#system-prompt"),
  systemCount: $("#system-count"),
  userMessage: $("#user-message"),
  messageCount: $("#message-count"),
  sendButton: $("#send-button"),
  sendHint: $("#send-hint"),
  answerCard: $(".answer-card"),
  answerOutput: $("#answer-output"),
  copyAnswer: $("#copy-answer"),
  toast: $("#toast"),
  debugModel: $("#debug-model"),
  debugDuration: $("#debug-duration"),
  debugInputTokens: $("#debug-input-tokens"),
  debugOutputTokens: $("#debug-output-tokens"),
  debugTotalTokens: $("#debug-total-tokens"),
  debugDiagnostic: $("#debug-diagnostic"),
  debugSystem: $("#debug-system"),
  debugUser: $("#debug-user"),
  debugRequest: $("#debug-request"),
  debugProviderRequest: $("#debug-provider-request"),
  debugProviderResponse: $("#debug-provider-response"),
  debugResponse: $("#debug-response"),
};

let configured = false;
let sending = false;
let latestAnswer = "";
let toastTimer;


function formatJson(value) {
  return JSON.stringify(value, null, 2);
}


function tokenText(value) {
  return Number.isInteger(value) ? value.toLocaleString("th-TH") : "ไม่มีข้อมูล";
}


function updateCounts() {
  elements.systemCount.textContent =
    elements.systemPrompt.value.length.toLocaleString("th-TH");
  elements.messageCount.textContent =
    elements.userMessage.value.length.toLocaleString("th-TH");
}


function showToast(message) {
  window.clearTimeout(toastTimer);
  elements.toast.textContent = message;
  elements.toast.classList.add("is-visible");
  toastTimer = window.setTimeout(() => {
    elements.toast.classList.remove("is-visible");
  }, 2200);
}


async function copyText(text, successMessage) {
  if (!text) {
    showToast("ยังไม่มีข้อความให้คัดลอก");
    return;
  }
  try {
    await navigator.clipboard.writeText(text);
    showToast(successMessage);
  } catch {
    showToast("คัดลอกไม่สำเร็จ กรุณาเลือกข้อความแล้วคัดลอกเอง");
  }
}


function updateSendState() {
  elements.sendButton.disabled = !configured || sending;
  if (sending) {
    elements.sendHint.textContent = "กำลังคุยกับ Gemini รอแปร๊บบ";
  } else if (configured) {
    elements.sendHint.textContent = "Gemini Ready!";
  } else {
    elements.sendHint.textContent = "ลืมตั้งค่า Gemini หรือป่าว? เช็คใน .env ไฟล์";
  }
}


async function loadStatus() {
  try {
    const response = await fetch("/api/chat", {
      headers: { Accept: "application/json" },
      cache: "no-store",
    });
    const data = await response.json();
    const provider = data.provider;
    if (!response.ok || !provider) {
      throw new Error("invalid status");
    }

    configured = provider.configured;
    elements.providerStatus.className =
      `provider-status ${configured ? "is-ready" : "is-error"}`;
    elements.providerStatus.querySelector("strong").textContent = provider.message;
    elements.activeModel.textContent = provider.model
      ? `Model: ${provider.model}`
      : "ยังไม่ได้ตั้งค่า Model";
    elements.debugModel.textContent = provider.model || "—";
  } catch {
    configured = false;
    elements.providerStatus.className = "provider-status is-error";
    elements.providerStatus.querySelector("strong").textContent =
      "ติดต่อ Python Backend ไม่ได้";
    elements.activeModel.textContent =
      "Local: เปิดด้วย server.py · Vercel: ตรวจ Deployment";
  }
  updateSendState();
}


function setLoading(value) {
  sending = value;
  elements.sendButton.classList.toggle("is-loading", value);
  elements.answerCard.setAttribute("aria-busy", String(value));
  updateSendState();
}


function showAnswer(text) {
  latestAnswer = text;
  elements.answerOutput.textContent = text;
  elements.copyAnswer.disabled = false;
}


function showError(message) {
  latestAnswer = "";
  elements.answerOutput.replaceChildren();
  const paragraph = document.createElement("p");
  paragraph.className = "error";
  paragraph.textContent = message;
  elements.answerOutput.append(paragraph);
  elements.copyAnswer.disabled = true;
}


function clearAnswer() {
  latestAnswer = "";
  elements.answerOutput.innerHTML =
    '<p class="placeholder">คำตอบจะปรากฏตรงนี้หลังจากกด “ส่งให้ Gemini”</p>';
  elements.copyAnswer.disabled = true;
  elements.debugDuration.textContent = "—";
  elements.debugInputTokens.textContent = "—";
  elements.debugOutputTokens.textContent = "—";
  elements.debugTotalTokens.textContent = "—";
  elements.debugDiagnostic.textContent = "—";
  elements.debugSystem.textContent = "ยังไม่ได้ส่ง";
  elements.debugUser.textContent = "ยังไม่ได้ส่ง";
  elements.debugRequest.textContent = "ยังไม่มี Request";
  elements.debugProviderRequest.textContent = "ยังไม่มี Provider Request";
  elements.debugProviderResponse.textContent = "ยังไม่มี Provider Response";
  elements.debugResponse.textContent = "ยังไม่มี Response";
}


function showLearningRequest(requestData) {
  elements.debugSystem.textContent =
    requestData.systemPrompt || "(ไม่ได้กำหนด System Prompt)";
  elements.debugUser.textContent = requestData.message;
  elements.debugRequest.textContent = formatJson(requestData);
  elements.debugProviderRequest.textContent =
    "Python กำลังเตรียม Request สำหรับ Gemini...";
  elements.debugProviderResponse.textContent =
    "ยังไม่ได้รับ Response จาก Gemini";
  elements.debugResponse.textContent =
    "กำลังรอ Response จาก Backend...";
  elements.debugDuration.textContent = "กำลังจับเวลา";
  elements.debugInputTokens.textContent = "—";
  elements.debugOutputTokens.textContent = "—";
  elements.debugTotalTokens.textContent = "—";
  elements.debugDiagnostic.textContent = "connecting";
}


function showLearningResponse(data, clientDuration) {
  const learning = data.learning || {};
  const backendResponse = { ...data };
  delete backendResponse.learning;

  elements.debugProviderRequest.textContent = learning.providerRequest
    ? formatJson(learning.providerRequest)
    : "Backend ไม่ได้ส่งข้อมูลขั้นนี้กลับมา";
  elements.debugProviderResponse.textContent = learning.providerResponse
    ? formatJson(learning.providerResponse)
    : "ไม่มี Provider Response";
  elements.debugResponse.textContent = formatJson(backendResponse);
  elements.debugDiagnostic.textContent =
    learning.diagnosticCode || data.code || (data.success ? "ok" : "unknown_error");
  elements.debugDuration.textContent = `${data.durationMs ?? clientDuration} ms`;

  const usage = data.usage || {};
  elements.debugInputTokens.textContent = tokenText(usage.inputTokens);
  elements.debugOutputTokens.textContent = tokenText(usage.outputTokens);
  elements.debugTotalTokens.textContent = tokenText(usage.totalTokens);
}


async function sendMessage() {
  if (sending) {
    return;
  }

  const message = elements.userMessage.value.trim();
  if (!message) {
    showError("กรุณาพิมพ์ข้อความก่อนส่งให้ AI");
    elements.userMessage.focus();
    return;
  }

  const requestData = {
    systemPrompt: elements.systemPrompt.value,
    message,
    learningMode: elements.learningMode.checked,
  };

  if (requestData.learningMode) {
    showLearningRequest(requestData);
  }

  setLoading(true);
  const startedAt = performance.now();
  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify(requestData),
    });

    let data;
    try {
      data = await response.json();
    } catch {
      throw new Error("Backend ส่งข้อมูลที่ไม่ใช่ JSON");
    }

    if (requestData.learningMode) {
      showLearningResponse(data, Math.round(performance.now() - startedAt));
    }

    if (!response.ok || !data.success) {
      showError(data.error || "เกิดข้อผิดพลาด กรุณาลองใหม่");
      return;
    }
    showAnswer(data.answer);
  } catch (error) {
    showError(error.message || "ติดต่อ Backend ไม่ได้");
    if (requestData.learningMode) {
      elements.debugDiagnostic.textContent = "browser_network_error";
      elements.debugDuration.textContent =
        `${Math.round(performance.now() - startedAt)} ms`;
      elements.debugResponse.textContent =
        "Browser ติดต่อ /api/chat ไม่สำเร็จ จึงไม่มี Response JSON";
    }
  } finally {
    setLoading(false);
  }
}


elements.learningMode.addEventListener("change", () => {
  elements.learningPanel.hidden = !elements.learningMode.checked;
});

elements.systemPrompt.addEventListener("input", updateCounts);
elements.userMessage.addEventListener("input", updateCounts);
elements.userMessage.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    sendMessage();
  }
});

$("#send-button").addEventListener("click", sendMessage);
$("#sample-system").addEventListener("click", () => {
  elements.systemPrompt.value = SAMPLE_SYSTEM_PROMPT;
  updateCounts();
});
$("#reset-system").addEventListener("click", () => {
  elements.systemPrompt.value = DEFAULT_SYSTEM_PROMPT;
  updateCounts();
});
$("#copy-system").addEventListener("click", () => {
  copyText(elements.systemPrompt.value, "คัดลอก System Prompt แล้ว");
});
$("#copy-answer").addEventListener("click", () => {
  copyText(latestAnswer, "คัดลอกคำตอบแล้ว");
});
$("#clear-answer").addEventListener("click", clearAnswer);

document.querySelectorAll("[data-prompt]").forEach((button) => {
  button.addEventListener("click", () => {
    elements.userMessage.value = button.dataset.prompt;
    updateCounts();
    elements.userMessage.focus();
  });
});

updateCounts();
clearAnswer();
loadStatus();

const API_BASE = import.meta.env.VITE_API_BASE || "http://127.0.0.1:8020";

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    credentials: "include",
    ...options,
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.detail || "THREAD AI request failed.");
  }
  return data;
}

export function googleSignInUrl() {
  return `${API_BASE}/api/auth/google/start`;
}

export function getCurrentUser() {
  return request("/api/auth/me");
}

export function getAuthConfig() {
  return request("/api/auth/config");
}

export function devLogin() {
  return request("/api/auth/dev-login", { method: "POST" });
}

export function logout() {
  return request("/api/auth/logout", { method: "POST" });
}

export function createChat(message, conversationId) {
  return request("/api/chat", {
    method: "POST",
    body: JSON.stringify({ message, conversation_id: conversationId }),
  });
}

export function enhancePrompt(prompt) {
  return request("/api/enhance-prompt", {
    method: "POST",
    body: JSON.stringify({ prompt }),
  });
}

export function createThread(payload) {
  return request("/api/threads", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function sendThreadMessage(threadId, question) {
  return request(`/api/threads/${threadId}/messages`, {
    method: "POST",
    body: JSON.stringify({ question }),
  });
}

export function getThread(threadId) {
  return request(`/api/threads/${threadId}`);
}

export function getResponseThreads(responseId) {
  return request(`/api/responses/${responseId}/threads`);
}

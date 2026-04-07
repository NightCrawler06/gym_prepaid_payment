import { API_BASE_URL } from "./apiConfig";

export async function initializeDatabase() {
  await apiRequest("health");
}

async function apiRequest(action, options = {}) {
  const response = await fetch(`${API_BASE_URL}/index.php?action=${action}`, {
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
    ...options,
  });

  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.error || "Request failed.");
  }

  return payload;
}

export async function createMember({ fullName, phone, email, initialCredits }) {
  const payload = await apiRequest("create_member", {
    method: "POST",
    body: JSON.stringify({
      fullName,
      phone,
      email,
      initialCredits,
    }),
  });

  return payload.member;
}

export async function getMembers() {
  const payload = await apiRequest("members");
  return payload.members;
}

export async function addCredits(memberId, amount) {
  await apiRequest("top_up", {
    method: "POST",
    body: JSON.stringify({
      memberId,
      amount,
    }),
  });
}

export async function processScanToken(scanToken) {
  return apiRequest("scan", {
    method: "POST",
    body: JSON.stringify({
      scanToken,
    }),
  });
}

export async function getLogs() {
  const payload = await apiRequest("logs");
  return payload.logs;
}

export async function getDashboardStats() {
  const payload = await apiRequest("stats");
  return payload.stats;
}

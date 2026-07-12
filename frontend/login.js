const form = document.querySelector("#loginForm");
const statusBox = document.querySelector("#backendStatus");
const loginButton = document.querySelector("#loginButton");
const agentField = document.querySelector("#agentField");
const providerField = document.querySelector("#providerField");
const errorBox = document.querySelector("#formError");

function populateWorkspaceChoices(agents, providers) {
  const agentSelect = document.querySelector("#agentSelect");
  const providerSelect = document.querySelector("#providerSelect");
  agentSelect.innerHTML = agents.slice(0, 2).map((agent) => (
    `<option value="${agent.id}">Agent ${agent.id} — ${agent.name}</option>`
  )).join("");
  providerSelect.innerHTML = providers.map((provider) => (
    `<option value="${provider.code}">${provider.display_name} Provider Operations</option>`
  )).join("");
}

function selectedRole() {
  return document.querySelector('input[name="role"]:checked').value;
}

function updateRoleUi() {
  const isAgent = selectedRole() === "agent";
  agentField.hidden = !isAgent;
  providerField.hidden = isAgent;
  loginButton.querySelector("span").textContent = isAgent
    ? "Open agent dashboard"
    : "Open provider dashboard";
  document.querySelectorAll(".role-option").forEach((option) => {
    option.classList.toggle("selected", option.querySelector("input").checked);
  });
}

async function checkBackend() {
  try {
    const response = await fetch(`${API_BASE_URL}/health`, {
      signal: AbortSignal.timeout(API_STARTUP_TIMEOUT_MS),
    });
    if (!response.ok) throw new Error("API did not return a successful response.");
    const payload = await response.json();
    if (payload.status !== "ok") throw new Error("API health check failed.");
    const [agentsResponse, providersResponse] = await Promise.all([
      fetch(`${API_BASE_URL}/agents`),
      fetch(`${API_BASE_URL}/providers`),
    ]);
    if (!agentsResponse.ok || !providersResponse.ok) {
      throw new Error("Could not load workspace choices from the API.");
    }
    populateWorkspaceChoices(await agentsResponse.json(), await providersResponse.json());

    statusBox.className = "backend-status ready";
    statusBox.innerHTML = '<span class="status-dot"></span><span>Deployed API connected</span>';
    loginButton.disabled = false;
  } catch (error) {
    statusBox.className = "backend-status offline";
    statusBox.innerHTML = '<span class="status-dot"></span><span>Deployed API unavailable</span>';
    errorBox.hidden = false;
    errorBox.textContent = `The deployed API could not be reached: ${error.message} It may still be starting; wait a moment and refresh. No login data was sent.`;
  }
}

document.querySelectorAll('input[name="role"]').forEach((input) => {
  input.addEventListener("change", updateRoleUi);
});

form.addEventListener("submit", (event) => {
  event.preventDefault();
  if (loginButton.disabled) return;

  const role = selectedRole();
  const session = { role, signedInAt: new Date().toISOString() };
  if (role === "agent") {
    session.agentId = Number(document.querySelector("#agentSelect").value);
  } else {
    session.providerCode = document.querySelector("#providerSelect").value;
  }
  sessionStorage.setItem("agentflow_demo_session", JSON.stringify(session));

  // These pages are intentionally separate because agent and provider views
  // will expose different responsibilities in the next implementation steps.
  window.location.assign(role === "agent" ? "agent_dashboard.html" : "provider_dashboard.html");
});

updateRoleUi();
checkBackend();

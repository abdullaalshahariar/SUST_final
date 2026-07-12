const form = document.querySelector("#loginForm");
const loginButton = document.querySelector("#loginButton");
const agentField = document.querySelector("#agentField");
const providerField = document.querySelector("#providerField");

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

document.querySelectorAll('input[name="role"]').forEach((input) => {
  input.addEventListener("change", updateRoleUi);
});

form.addEventListener("submit", (event) => {
  event.preventDefault();

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

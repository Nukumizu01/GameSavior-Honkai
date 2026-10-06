const form = document.querySelector("#login-form");
const button = form.querySelector("button");
const error = document.querySelector("#login-error");

function showError(message) {
  error.textContent = message;
  error.hidden = false;
}

async function checkExistingSession() {
  const response = await fetch("/api/v1/auth/me", { credentials: "include" });
  if (response.ok) window.location.replace("/dashboard");
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  error.hidden = true;
  button.disabled = true;
  try {
    const response = await fetch("/api/v1/auth/login", {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        username: document.querySelector("#username").value,
        password: document.querySelector("#password").value,
      }),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || "用户名或密码错误");
    window.location.replace("/dashboard");
  } catch (loginError) {
    showError(loginError.message || "登录失败，请稍后重试");
    button.disabled = false;
  }
});

checkExistingSession().catch(() => {});

// Contact form → POST /api/contact → render the AI analysis returned by the backend.
(() => {
  "use strict";

  const form = document.getElementById("contact-form");
  const result = document.getElementById("result");
  const submitBtn = document.getElementById("submit-btn");
  const yearEl = document.getElementById("year");
  if (yearEl) yearEl.textContent = new Date().getFullYear();

  const fields = ["name", "email", "phone", "comment"];

  function setError(name, message) {
    const input = document.getElementById(name);
    const field = input.closest(".field");
    let err = field.querySelector(".err");
    if (!err) {
      err = document.createElement("span");
      err.className = "err";
      field.appendChild(err);
    }
    err.textContent = message || "";
    field.classList.toggle("invalid", Boolean(message));
  }

  function clearErrors() {
    fields.forEach((f) => setError(f, ""));
  }

  function validate(data) {
    let ok = true;
    if (!data.name || data.name.trim().length < 2) {
      setError("name", "Укажите имя (минимум 2 символа).");
      ok = false;
    }
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(data.email)) {
      setError("email", "Введите корректный email.");
      ok = false;
    }
    if (!/^\+?[0-9][0-9\s\-()]{6,19}$/.test(data.phone)) {
      setError("phone", "Введите корректный телефон.");
      ok = false;
    }
    if (!data.comment || data.comment.trim().length < 5) {
      setError("comment", "Сообщение слишком короткое.");
      ok = false;
    }
    return ok;
  }

  function renderSuccess(payload) {
    const a = payload.analysis || {};
    const email = payload.email_status || {};
    result.hidden = false;
    result.className = "result ok";
    result.innerHTML = `
      <h3>✅ Обращение принято</h3>
      <div class="tags">
        <span class="tag ${escapeAttr(a.sentiment)}">${escapeHtml(a.sentiment)}</span>
        <span class="tag">${escapeHtml(a.category)}</span>
        <span class="tag ${escapeAttr(a.priority)}">${escapeHtml(a.priority)}</span>
      </div>
      <p style="color:var(--muted);margin:0 0 10px">${escapeHtml(a.summary)}</p>
      <p style="font-size:13px;color:var(--muted);margin:0 0 6px">Черновик ответа от AI:</p>
      <p class="reply">${escapeHtml(a.suggested_reply)}</p>
      <p class="meta">id ${escapeHtml(payload.id)} · ai:${escapeHtml(a.source)} ·
        email owner:${escapeHtml(email.owner)} / user:${escapeHtml(email.user)}</p>
    `;
    result.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  function renderError(message) {
    result.hidden = false;
    result.className = "result fail";
    result.innerHTML = `<h3>⚠️ Не отправлено</h3><p style="color:var(--muted);margin:0">${escapeHtml(
      message
    )}</p>`;
  }

  function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>"']/g, (c) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;",
    }[c]));
  }
  function escapeAttr(value) {
    return String(value ?? "").replace(/[^a-z]/gi, "");
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    clearErrors();
    result.hidden = true;

    const data = {
      name: form.name.value,
      email: form.email.value,
      phone: form.phone.value,
      comment: form.comment.value,
    };
    if (!validate(data)) return;

    submitBtn.disabled = true;
    submitBtn.textContent = "Отправка…";

    try {
      const res = await fetch("/api/contact", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data),
      });
      const body = await res.json().catch(() => ({}));

      if (res.status === 201) {
        renderSuccess(body);
        form.reset();
      } else if (res.status === 429) {
        const retry = body?.error?.details?.retry_after_seconds;
        renderError(
          `Слишком много запросов. Попробуйте через ${retry ?? "несколько"} сек.`
        );
      } else if (res.status === 422) {
        renderError("Проверьте корректность заполнения полей.");
      } else {
        renderError(body?.error?.message || "Произошла ошибка. Попробуйте позже.");
      }
    } catch (err) {
      renderError("Сеть недоступна. Проверьте подключение.");
    } finally {
      submitBtn.disabled = false;
      submitBtn.textContent = "Отправить";
    }
  });
})();

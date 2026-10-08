"use strict";

class FormChanges {
  static between(original, submitted) {
    return Object.fromEntries(
      Object.entries(submitted).filter(
        ([key, value]) => value !== original[key],
      ),
    );
  }
}
class HelpdeskApp {
  $ = (s, root = document) => root.querySelector(s);
  esc = (value) =>
    String(value ?? "").replace(
      /[&<>"']/g,
      (c) =>
        ({
          "&": "&amp;",
          "<": "&lt;",
          ">": "&gt;",
          '"': "&quot;",
          "'": "&#39;",
        })[c],
    );
  statuses = {
    new: "Новая",
    in_progress: "В работе",
    closed: "Закрыта",
  };
  roles = {
    customer: "Пользователь",
    support: "Поддержка",
    admin: "Администратор",
  };
  token = "";
  user = null;
  renderId = 0;
  page = 0;
  cursors = [null];
  categoryFilter = "";
  statusFilter = "";
  commentCursors = [null];
  commentPage = 0;
  drafts = new Map();
  date = (v) =>
    new Date(v).toLocaleString("ru-RU", {
      day: "2-digit",
      month: "short",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  duration = (seconds) => {
    const micros = Math.round(Math.max(0, seconds) * 1_000_000);
    const hours = Math.floor(micros / 3_600_000_000);
    const minutes = Math.floor((micros % 3_600_000_000) / 60_000_000);
    const rest = (micros % 60_000_000) / 1_000_000;
    const parts = [];
    if (hours) parts.push(`${hours} ч`);
    if (minutes) parts.push(`${minutes} мин`);
    if (rest || !parts.length)
      parts.push(
        `${rest.toLocaleString("ru-RU", {
          maximumFractionDigits: 6,
          useGrouping: false,
        })} с`,
      );
    return parts.join(" ");
  };
  badge = (status) =>
    `<span class="badge ${this.esc(status)}">${this.esc(this.statuses[status] || status)}</span>`;
  notice(text) {
    this.$("#notice").textContent = text;
    setTimeout(() => {
      this.$("#notice").textContent = "";
    }, 4500);
  }
  async api(path, options = {}) {
    const requestToken = this.token;
    const response = await fetch("/api/v1" + path, {
      cache: "no-store",
      ...options,
      headers: {
        ...(this.token
          ? {
              Authorization: `Bearer ${this.token}`,
            }
          : {}),
        ...(options.body
          ? {
              "Content-Type": "application/json",
            }
          : {}),
        ...options.headers,
      },
    });
    const data = await response.json();
    if (!response.ok) {
      if (
        response.status === 401 &&
        this.token &&
        this.token === requestToken
      ) {
        this.token = "";
        this.user = null;
        this.drafts.clear();
        this.loginView();
      }
      let message = data.detail || "Не удалось выполнить запрос";
      if (response.status === 400 && data.extra)
        message = "Проверьте заполнение полей и допустимые значения.";
      throw new Error(
        typeof message === "string" ? message : "Проверьте заполнение полей",
      );
    }
    return data;
  }
  send = (path, method, data) =>
    this.api(path, {
      method,
      body: JSON.stringify(data),
    });
  async allPages(path, params = {}) {
    const requestToken = this.token;
    let result = [],
      cursor = null;
    do {
      const data = await this.api(
        path +
          "?" +
          new URLSearchParams({
            ...params,
            limit: 100,
            ...(cursor
              ? {
                  cursor,
                }
              : {}),
          }),
      );
      if (requestToken !== this.token) throw new Error("Сессия изменилась");
      result.push(...data.items);
      cursor = data.next_cursor;
    } while (cursor);
    return result;
  }
  icon(name) {
    const paths = {
      tickets:
        '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M7 8h10M7 12h7M7 16h4"/>',
      summary: '<path d="M4 4v16h16M8 16v-4M12 16V8M16 16V5"/>',
      users:
        '<circle cx="9" cy="8" r="3"/><path d="M3 20v-2a6 6 0 0 1 12 0v2M16 5a3 3 0 0 1 0 6M17 14a5 5 0 0 1 4 4v2"/>',
      settings:
        '<path d="M4 7h16M4 17h16"/><circle cx="9" cy="7" r="3" fill="currentColor"/><circle cx="15" cy="17" r="3" fill="currentColor"/>',
      plus: '<path d="M12 5v14M5 12h14"/>',
      refresh:
        '<path d="M20 7v5h-5M4 17v-5h5M6 6a8 8 0 0 1 13 4M18 18a8 8 0 0 1-13-4"/>',
      left: '<path d="m14 6-6 6 6 6"/>',
      right: '<path d="m10 6 6 6-6 6"/>',
      logout: '<path d="M9 4H4v16h5M10 12h10m-4-4 4 4-4 4"/>',
    };
    return `<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths[name] || paths.tickets}</svg>`;
  }
  brand() {
    return '<div class="brand"><b>Служба поддержки</b></div>';
  }
  loginView() {
    this.renderId++;
    this.$("#dialog").close();
    this.$("#app").innerHTML =
      `<div class="login"><header class="login-header">${this.brand()}</header><main class="login-main"><section class="login-card"><h1>Вход в службу поддержки</h1><p class="muted">Введите данные своей учётной записи.</p><form id="login-form"><label for="login-name">Логин</label><input id="login-name" name="login" autocomplete="username" required pattern="[a-z][a-z0-9_]{2,63}"><label for="login-password">Пароль</label><input id="login-password" name="password" type="password" autocomplete="current-password" required maxlength="128"><div class="error" role="alert"></div><button class="primary">Войти</button></form></section></main></div>`;
    this.$("#login-form").onsubmit = (e) =>
      this.submit(e, async (data) => {
        const result = await this.send("/auth/login", "POST", data);
        this.token = result.access_token;
        this.user = result.user;
        this.page = 0;
        this.cursors = [null];
        const destination =
          this.user.role === "admin" ? "#admin/categories" : "#tickets";
        if (location.hash === destination) await this.render();
        else location.hash = destination;
      });
  }
  async submit(event, action) {
    event.preventDefault();
    const form = event.currentTarget;
    const button = this.$('button[type="submit"],button:not([type])', form);
    if (button) button.disabled = true;
    this.$(".error", form)?.replaceChildren();
    try {
      await action(Object.fromEntries(new FormData(form)));
    } catch (error) {
      const box = this.$(".error", form);
      if (box) box.textContent = error.message;
      else this.notice(error.message);
    } finally {
      if (button) button.disabled = false;
    }
  }
  shell(route) {
    const isTickets = route.startsWith("tickets");
    const navLink = (path, label, symbol) =>
      `<a href="#${path}" ${route === path ? 'aria-current="page"' : ""}>${this.icon(symbol)}<span>${label}</span></a>`;
    const queues = [
      ["", "Все заявки"],
      ["new", "Новые"],
      ["in_progress", "В работе"],
      ["closed", "Закрытые"],
    ];
    let navigation;
    if (this.user.role === "admin") {
      navigation =
        '<div class="nav-label">Администрирование</div>' +
        navLink("admin/categories", "Категории и нормативы", "settings") +
        navLink("admin/users", "Пользователи", "users") +
        '<div class="nav-divider"></div>' +
        navLink("summary", "Сводка", "summary");
    } else if (this.user.role === "support") {
      navigation =
        '<div class="nav-label">Очереди заявок</div>' +
        queues
          .map(
            ([status, label]) =>
              `<a href="#tickets" data-queue="${status}" ${isTickets && this.statusFilter === status ? 'aria-current="page"' : ""}>${status ? '<span class="queue-dot ' + status + '"></span>' : this.icon("tickets")}<span>${label}</span></a>`,
          )
          .join("") +
        '<div class="nav-divider"></div>' +
        navLink("summary", "Сводка", "summary");
    } else {
      navigation =
        '<div class="nav-label">Личный кабинет</div>' +
        navLink("tickets", "Мои заявки", "tickets") +
        navLink("tickets/new", "Создать заявку", "plus");
    }
    this.$("#app").innerHTML =
      `<div class="shell"><header class="topbar">${this.brand()}<div class="account"><span class="account-name" title="${this.esc(this.user.display_name)}">${this.esc(this.user.login)}</span><span class="account-role">${this.roles[this.user.role]}</span><button class="text-button" id="logout" title="Выйти из аккаунта">${this.icon("logout")}<span>Выйти</span></button></div></header><aside class="sidebar"><nav class="nav" aria-label="Основная навигация">${navigation}</nav><div class="sidebar-footer"><span class="small muted">${this.esc(this.user.login)}</span><span class="small muted">${this.roles[this.user.role]}</span></div></aside><main id="content" class="content"><div class="loading" role="status">Загрузка…</div></main></div>`;
    this.$("#logout").onclick = () => {
      this.token = "";
      this.user = null;
      this.drafts.clear();
      this.statusFilter = "";
      this.categoryFilter = "";
      this.loginView();
    };
    document.querySelectorAll("[data-queue]").forEach(
      (link) =>
        (link.onclick = (event) => {
          event.preventDefault();
          this.statusFilter = link.dataset.queue;
          this.categoryFilter = "";
          this.resetPage();
          if (location.hash === "#tickets") this.render();
          else location.hash = "tickets";
        }),
    );
  }
  heading(title, subtitle, actions = "") {
    return `<header class="pagehead"><div><h1>${this.esc(title)}</h1>${subtitle ? `<p class="muted">${this.esc(subtitle)}</p>` : ""}</div><div class="page-actions">${actions}</div></header>`;
  }
  pager(nextCursor) {
    return `<div class="pager"><span>Страница ${this.page + 1}</span><div class="actions"><button id="prev" ${this.page === 0 ? "disabled" : ""}>${this.icon("left")}Назад</button><button id="next" ${nextCursor ? "" : "disabled"}>Далее${this.icon("right")}</button></div></div>`;
  }
  wirePager(cursor) {
    this.$("#prev").onclick = () => {
      this.page--;
      this.render();
    };
    this.$("#next").onclick = () => {
      this.cursors[++this.page] = cursor;
      this.render();
    };
  }
  resetPage() {
    this.page = 0;
    this.cursors = [null];
  }
  query(extra = {}) {
    return new URLSearchParams({
      limit: 20,
      ...extra,
      ...(this.cursors[this.page]
        ? {
            cursor: this.cursors[this.page],
          }
        : {}),
    });
  }
  async render() {
    if (!this.user) return this.loginView();
    const id = ++this.renderId,
      route = location.hash.slice(1) || "tickets";
    this.shell(route);
    const draw = (html) => {
      if (id === this.renderId) this.$("#content").innerHTML = html;
      return id === this.renderId;
    };
    try {
      if (route === "tickets/new") await this.newTicket(draw);
      else if (/^tickets\/\d+$/.test(route))
        await this.ticketDetail(Number(route.split("/")[1]), draw);
      else if (route === "summary") await this.summaryView(draw);
      else if (route === "admin/categories") await this.categoriesView(draw);
      else if (route === "admin/users") await this.usersView(draw);
      else await this.ticketsView(draw);
    } catch (error) {
      draw(
        `${this.heading("Не удалось открыть страницу", "Попробуйте обновить данные.")}<div class="error" role="alert">${this.esc(error.message)}</div><p><button id="retry">Повторить</button></p>`,
      );
      const retry = this.$("#retry");
      if (retry) retry.onclick = () => this.render();
    }
  }
  async ticketsView(draw) {
    const categories = await this.allPages("/categories", {
      include_inactive: true,
    });
    const data = await this.api(
      "/tickets?" +
        this.query({
          ...(this.categoryFilter
            ? {
                category_id: this.categoryFilter,
              }
            : {}),
          ...(this.statusFilter
            ? {
                status: this.statusFilter,
              }
            : {}),
        }),
    );
    const names = Object.fromEntries(categories.map((c) => [c.id, c.name]));
    const title =
      this.user.role === "customer"
        ? "Мои заявки"
        : {
            new: "Новые заявки",
            in_progress: "Заявки в работе",
            closed: "Закрытые заявки",
          }[this.statusFilter] || "Все заявки";
    if (
      !draw(
        this.heading(
          title,
          "",
          this.user.role === "customer"
            ? `<a class="button primary" href="#tickets/new">${this.icon("plus")}Создать заявку</a>`
            : "",
        ) +
          `
    <section class="ticket-list" aria-label="Список заявок"><div class="filters">
      <label for="filter-category">Категория</label><select id="filter-category"><option value="">Все категории</option>${categories.map((c) => `<option value="${c.id}" ${String(c.id) === this.categoryFilter ? "selected" : ""}>${this.esc(c.name)}</option>`).join("")}</select>
      <label for="filter-status">Статус</label><select id="filter-status"><option value="">Все статусы</option>${Object.entries(
        this.statuses,
      )
        .map(
          ([key, label]) =>
            `<option value="${key}" ${this.statusFilter === key ? "selected" : ""}>${label}</option>`,
        )
        .join("")}</select>
      ${this.categoryFilter || this.statusFilter ? '<button class="text-button" id="reset-filters">Сбросить</button>' : ""}<button class="push" id="refresh">${this.icon("refresh")}Обновить</button>
    </div><div class="list-meta"><span>${data.items.length} на странице</span><span>По номеру <span aria-hidden="true">↓</span></span></div>
    ${data.items.length ? `<div class="tablewrap"><table class="tickets-table"><thead><tr><th scope="col">Номер</th><th scope="col">Тема</th><th scope="col">Автор</th><th scope="col">Категория</th><th scope="col">Статус</th><th scope="col">Создано</th></tr></thead><tbody>${data.items.map((t) => `<tr><td class="ticket-number"><a href="#tickets/${t.id}">#${t.id}</a></td><td class="ticket-subject"><a href="#tickets/${t.id}" title="${this.esc(t.title)}">${this.esc(t.title)}</a></td><td class="requester">${this.esc(t.author_login)}</td><td class="category-cell">${this.esc(names[t.category_id] || `Категория #${t.category_id}`)}</td><td>${this.badge(t.status)}</td><td class="date-cell">${this.date(t.created_at)}</td></tr>`).join("")}</tbody></table></div>` : '<div class="empty"><h2>Заявок нет</h2><p>По выбранным условиям ничего не найдено.</p></div>'}${this.pager(data.next_cursor)}</section>`,
      )
    )
      return;
    this.wirePager(data.next_cursor);
    this.$("#refresh").onclick = () => {
      this.resetPage();
      this.render();
    };
    if (this.$("#reset-filters"))
      this.$("#reset-filters").onclick = () => {
        this.categoryFilter = "";
        this.statusFilter = "";
        this.resetPage();
        this.render();
      };
    this.$("#filter-category").onchange = (e) => {
      this.categoryFilter = e.target.value;
      this.resetPage();
      this.render();
    };
    this.$("#filter-status").onchange = (e) => {
      this.statusFilter = e.target.value;
      this.resetPage();
      this.render();
    };
  }
  async newTicket(draw) {
    const categories = await this.allPages("/categories");
    if (
      !draw(
        `<a class="back" href="#tickets">← К моим заявкам</a>${this.heading("Новое обращение", "Опишите проблему — поддержка поможет с решением.")}<section class="panel pad wide-form"><form id="create-ticket"><label>Категория<select name="category_id" required><option value="">Выберите категорию</option>${categories.map((c) => `<option value="${c.id}">${this.esc(c.name)}</option>`).join("")}</select></label><label>Тема<input name="title" required maxlength="200" placeholder="Кратко опишите проблему"></label><label>Описание<textarea name="body" required maxlength="10000" rows="7" placeholder="Что произошло и какая помощь нужна?"></textarea></label><div class="error" role="alert"></div><div class="actions"><button class="primary">Отправить заявку</button><a href="#tickets">Отмена</a></div></form></section>`,
      )
    )
      return;
    this.$("#create-ticket").onsubmit = (e) =>
      this.submit(e, async (data) => {
        const requestToken = this.token;
        const view = this.renderId;
        data.category_id = Number(data.category_id);
        const result = await this.send("/tickets", "POST", data);
        if (this.token !== requestToken || this.renderId !== view) return;
        this.notice("Заявка создана");
        location.hash = `tickets/${result.id}`;
      });
  }
  async ticketDetail(ticketId, draw) {
    const ticket = await this.api(`/tickets/${ticketId}`);
    const comments = await this.api(
      `/tickets/${ticketId}/comments?` +
        new URLSearchParams({
          limit: 20,
          newest_first: true,
          ...(this.commentCursors[this.commentPage]
            ? {
                cursor: this.commentCursors[this.commentPage],
              }
            : {}),
        }),
    );
    const sla = ticket.reaction;
    const closedWithoutReply =
      ticket.status === "closed" && !sla.first_staff_reply_at;
    const authorLabel = (login) =>
      login === this.user.login
        ? "Вы"
        : login === ticket.author_login
          ? ticket.author_name
          : login;
    const next =
      ticket.status === "new"
        ? "in_progress"
        : ticket.status === "in_progress"
          ? "closed"
          : null;
    if (
      !draw(
        `<div class="breadcrumb"><a href="#tickets">Заявки</a><span aria-hidden="true">/</span><span>#${ticket.id}</span></div>${this.heading(ticket.title, "", this.badge(ticket.status))}<div class="detail-grid"><section class="conversation"><div class="section-heading"><h2>Переписка</h2><span class="muted small">Заявка #${ticket.id}</span></div><article class="message original-message"><div class="message-avatar" aria-hidden="true">${this.esc(authorLabel(ticket.author_login).slice(0, 1).toUpperCase())}</div><div class="message-content"><div class="comment-head"><strong>${this.esc(authorLabel(ticket.author_login))}</strong><span class="muted">Создание заявки</span><time>${this.date(ticket.created_at)}</time></div><p class="prewrap">${this.esc(ticket.body)}</p></div></article>${[
          ...comments.items,
        ]
          .reverse()
          .map(
            (c) =>
              `<article class="message ${c.is_staff_reply ? "staff" : ""}"><div class="message-avatar" aria-hidden="true">${this.esc(authorLabel(c.author_login).slice(0, 1).toUpperCase())}</div><div class="message-content"><div class="comment-head"><strong>${this.esc(authorLabel(c.author_login))}</strong>${c.is_staff_reply ? '<span class="staff-label">Поддержка</span>' : ""}<time>${this.date(c.created_at)}</time></div><p class="prewrap">${this.esc(c.body)}</p></div></article>`,
          )
          .join(
            "",
          )}<div class="comment-pager"><span>${this.commentPage === 0 ? "Последние комментарии" : "Предыдущие комментарии"}</span><div class="actions"><button id="comments-prev" ${comments.has_more ? "" : "disabled"}>${this.icon("left")}Ранее</button><button id="comments-next" ${this.commentPage === 0 ? "disabled" : ""}>Позже${this.icon("right")}</button></div></div>${ticket.status !== "closed" ? `<form id="reply-form" class="reply-composer"><label for="reply-body">${this.user.role === "support" ? "Ответ пользователю" : "Ваш комментарий"}</label><textarea id="reply-body" name="body" required maxlength="10000" placeholder="Введите сообщение…" rows="5"></textarea><div class="error" role="alert"></div><div class="composer-footer"><span class="small muted">Сообщение будет видно участникам заявки</span><button class="primary">Отправить</button></div></form>` : `<div class="closed-notice">Заявка закрыта. Переписка доступна для просмотра.</div>${this.drafts.get(ticketId) ? '<label>Неотправленный черновик<textarea id="reply-body" readonly></textarea></label>' : ""}`}</section><aside class="ticket-properties"><section><h2>Свойства заявки</h2><dl class="metadata"><div><dt>Статус</dt><dd>${this.badge(ticket.status)}</dd></div><div><dt>Категория</dt><dd>${this.esc(ticket.category.name)}</dd></div><div><dt>Автор</dt><dd>${this.esc(authorLabel(ticket.author_login))}<span class="muted small block">${this.esc(ticket.author_login)}</span></dd></div><div><dt>Создана</dt><dd>${this.date(ticket.created_at)}</dd></div>${ticket.closed_at ? `<div><dt>Закрыта</dt><dd>${this.date(ticket.closed_at)}</dd></div>` : ""}</dl>${this.user.role === "support" && next ? `<button class="primary status-action" id="change-status">${next === "in_progress" ? "Взять в работу" : "Закрыть заявку"}</button>` : ""}</section><section class="sla-section"><h2>Первая реакция</h2>${closedWithoutReply ? '<p class="small muted">Закрыта без ответа поддержки</p>' : ""}<div class="sla-state ${sla.breached ? "overdue" : ""}">${sla.breached ? "Норматив нарушен" : "В пределах норматива"}</div><dl class="metadata"><div><dt>Норматив</dt><dd>${this.duration(sla.norm_seconds)}</dd></div><div><dt>${sla.first_staff_reply_at ? "Время реакции" : closedWithoutReply ? "Ожидание до закрытия" : "Ожидание ответа"}</dt><dd>${this.duration(sla.elapsed_seconds)}</dd></div><div><dt>Первый ответ</dt><dd>${sla.first_staff_reply_at ? this.date(sla.first_staff_reply_at) : closedWithoutReply ? "Не было" : "Ответа пока нет"}</dd></div></dl></section></aside></div>`,
      )
    )
      return;
    const reply = this.$("#reply-body");
    if (reply) {
      reply.value = this.drafts.get(ticketId) || "";
      reply.oninput = () => this.drafts.set(ticketId, reply.value);
    }
    this.$("#comments-prev").onclick = () => {
      this.commentCursors[++this.commentPage] = comments.next_cursor;
      this.render();
    };
    this.$("#comments-next").onclick = () => {
      this.commentPage--;
      this.render();
    };
    if (this.$("#reply-form"))
      this.$("#reply-form").onsubmit = (e) =>
        this.submit(e, async (data) => {
          const requestToken = this.token;
          await this.send(`/tickets/${ticketId}/comments`, "POST", data);
          if (this.token !== requestToken) return;
          if (this.drafts.get(ticketId) === data.body)
            this.drafts.delete(ticketId);
          this.notice("Сообщение отправлено");
          if (location.hash === `#tickets/${ticketId}`) {
            this.commentPage = 0;
            this.commentCursors = [null];
            await this.render();
          }
        });
    if (this.$("#change-status"))
      this.$("#change-status").onclick = async (e) => {
        if (next === "closed" && (this.drafts.get(ticketId) || "").trim()) {
          this.notice("Сначала отправьте или удалите черновик ответа.");
          return;
        }
        const requestToken = this.token;
        const button = e.currentTarget;
        button.disabled = true;
        try {
          await this.send(`/tickets/${ticketId}/status`, "PATCH", {
            status: next,
          });
          if (requestToken !== this.token) return;
          this.notice("Статус обновлён");
          if (location.hash === `#tickets/${ticketId}`) await this.render();
        } catch (error) {
          this.notice(error.message);
          button.disabled = false;
        }
      };
  }
  async summaryView(draw) {
    const data = await this.api("/summary");
    const share = data.open_count ? data.breached_count / data.open_count : 0;
    if (
      !draw(
        this.heading(
          "Сводка",
          "Открытые заявки по категориям",
          `<button id="refresh">${this.icon("refresh")}Обновить</button>`,
        ) +
          `<div class="stats"><div class="stat"><span>Открыто</span><strong>${data.open_count.toLocaleString("ru-RU")}</strong></div><div class="stat alert"><span>С нарушением норматива</span><strong>${data.breached_count.toLocaleString("ru-RU")}</strong></div><div class="stat"><span>Доля нарушений</span><strong>${(share * 100).toFixed(1)}<small>%</small></strong></div></div><section class="summary-table"><div class="section-heading"><h2>По категориям</h2><span class="small muted">На ${this.date(data.as_of)}</span></div><div class="tablewrap"><table><thead><tr><th scope="col">Категория</th><th scope="col" class="numeric">Открыто</th><th scope="col" class="numeric">С нарушением</th><th scope="col">Доля нарушений</th></tr></thead><tbody>${data.items.map((row) => `<tr><td class="subject">${this.esc(row.category_name)}</td><td class="numeric">${row.open_count.toLocaleString("ru-RU")}</td><td class="numeric ${row.breached_count ? "breach-count" : ""}">${row.breached_count.toLocaleString("ru-RU")}</td><td><div class="ratio"><progress max="1" value="${row.breached_share}" aria-label="Доля нарушений в категории ${this.esc(row.category_name)}"></progress><span>${(row.breached_share * 100).toFixed(1)}%</span></div></td></tr>`).join("")}</tbody></table></div><p class="table-note">Учитываются заявки со статусом «Новая» и «В работе». Норматив — время до первого ответа поддержки.</p></section>`,
      )
    )
      return;
    this.$("#refresh").onclick = () => this.render();
  }
  modal(title, fields, onSubmit) {
    const dialog = this.$("#dialog");
    dialog.innerHTML = `<button type="button" class="close" aria-label="Закрыть">×</button><h2>${this.esc(title)}</h2><form>${fields}<div class="error" role="alert"></div><div class="actions"><button class="primary">Сохранить</button><button type="button" class="cancel">Отмена</button></div></form>`;
    this.$(".close", dialog).onclick = this.$(".cancel", dialog).onclick = () =>
      dialog.close();
    this.$("form", dialog).onsubmit = (e) =>
      this.submit(e, async (data) => {
        const form = e.currentTarget;
        const requestToken = this.token;
        await onSubmit(data);
        if (this.token !== requestToken || !form.isConnected) return;
        dialog.close();
        this.notice("Изменения сохранены");
        await this.render();
      });
    dialog.showModal();
  }
  categoryFields = (c = {}, seconds = 3600) =>
    `<label>Название<input name="name" maxlength="120" required value="${this.esc(c.name)}"></label><label>Описание<textarea name="description" maxlength="2000">${this.esc(c.description)}</textarea></label>${c.id ? `<label>Доступность<select name="is_active"><option value="true" ${c.is_active ? "selected" : ""}>Активна</option><option value="false" ${!c.is_active ? "selected" : ""}>Отключена</option></select></label>` : `<label>Норматив ответа, секунд<input name="response_seconds" type="number" min="1" max="2592000" required value="${seconds}"></label>`}`;
  async categoriesView(draw) {
    const data = await this.api("/admin/categories?" + this.query());
    const norms = Object.fromEntries(
      (await this.allPages("/admin/norms")).map((n) => [
        n.category_id,
        n.response_seconds,
      ]),
    );
    if (
      !draw(
        this.heading(
          "Категории и нормативы",
          "Настройка направлений поддержки и срока первой реакции.",
          '<button class="primary" id="add-category">Добавить категорию</button>',
        ) +
          `<section class="panel"><div class="tablewrap"><table><thead><tr><th>Категория</th><th>Норматив</th><th>Доступность</th><th>Действия</th></tr></thead><tbody>${data.items.map((c) => `<tr><td class="subject">${this.esc(c.name)}<small>${this.esc(c.description)}</small></td><td>${this.duration(norms[c.id])}</td><td><span class="badge ${c.is_active ? "in_progress" : "closed"}">${c.is_active ? "Активна" : "Отключена"}</span></td><td><div class="actions"><button data-category="${c.id}">Изменить</button><button data-norm="${c.id}">Норматив</button></div></td></tr>`).join("")}</tbody></table></div>${data.items.length ? "" : '<div class="empty">Добавьте первую категорию.</div>'}${this.pager(data.next_cursor)}</section>`,
      )
    )
      return;
    this.wirePager(data.next_cursor);
    this.$("#add-category").onclick = () =>
      this.modal("Новая категория", this.categoryFields(), (data) =>
        this.send("/admin/categories", "POST", {
          ...data,
          response_seconds: Number(data.response_seconds),
        }),
      );
    document.querySelectorAll("[data-category]").forEach(
      (button) =>
        (button.onclick = () => {
          const c = data.items.find(
            (c) => c.id === Number(button.dataset.category),
          );
          this.modal(
            "Изменить категорию",
            this.categoryFields(c),
            async (data) => {
              data.is_active = data.is_active === "true";
              const changes = FormChanges.between(c, data);
              if (Object.keys(changes).length)
                await this.send(`/admin/categories/${c.id}`, "PATCH", changes);
            },
          );
        }),
    );
    document.querySelectorAll("[data-norm]").forEach(
      (button) =>
        (button.onclick = () => {
          const id = Number(button.dataset.norm);
          this.modal(
            "Норматив первой реакции",
            `<p class="small muted">Новый норматив будет действовать для новых заявок.</p><label>Срок в секундах<input name="response_seconds" type="number" min="1" max="2592000" required value="${norms[id]}"></label>`,
            (data) =>
              this.send(`/admin/norms/${id}`, "PUT", {
                response_seconds: Number(data.response_seconds),
              }),
          );
        }),
    );
  }
  userFields(u = {}) {
    return `${!u.login ? '<label>Логин<input name="login" required pattern="[a-z][a-z0-9_]{2,63}" placeholder="Латинские буквы, цифры, _"></label>' : ""}<label>Имя<input name="display_name" required maxlength="120" value="${this.esc(u.display_name)}"></label><label>Роль<select name="role">${Object.entries(
      this.roles,
    )
      .map(
        ([r, n]) =>
          `<option value="${r}" ${u.role === r ? "selected" : ""}>${n}</option>`,
      )
      .join(
        "",
      )}</select></label>${u.login ? `<label>Доступ<select name="is_active"><option value="true" ${u.is_active ? "selected" : ""}>Активен</option><option value="false" ${!u.is_active ? "selected" : ""}>Заблокирован</option></select></label>` : ""}<label>${u.login ? "Новый пароль (необязательно)" : "Пароль"}<input name="password" type="password" autocomplete="new-password" minlength="10" maxlength="128" ${u.login ? "" : "required"}></label>`;
  }
  async usersView(draw) {
    const data = await this.api("/admin/users?" + this.query());
    if (
      !draw(
        this.heading(
          "Пользователи",
          "Учётные записи, роли и доступ к сервису.",
          '<button class="primary" id="add-user">Добавить пользователя</button>',
        ) +
          `<section class="panel"><div class="tablewrap"><table><thead><tr><th>Пользователь</th><th>Роль</th><th>Доступ</th><th></th></tr></thead><tbody>${data.items.map((u) => `<tr><td class="subject">${this.esc(u.display_name)}<small>${this.esc(u.login)}</small></td><td>${this.roles[u.role]}</td><td><span class="badge ${u.is_active ? "in_progress" : "closed"}">${u.is_active ? "Активен" : "Заблокирован"}</span></td><td><button data-user="${this.esc(u.login)}">Изменить</button></td></tr>`).join("")}</tbody></table></div>${this.pager(data.next_cursor)}</section>`,
      )
    )
      return;
    this.wirePager(data.next_cursor);
    this.$("#add-user").onclick = () =>
      this.modal("Новый пользователь", this.userFields(), (data) =>
        this.send("/admin/users", "POST", data),
      );
    document.querySelectorAll("[data-user]").forEach(
      (button) =>
        (button.onclick = () => {
          const u = data.items.find((u) => u.login === button.dataset.user);
          this.modal(
            "Изменить пользователя",
            this.userFields(u),
            async (data) => {
              if (!data.password) delete data.password;
              data.is_active = data.is_active === "true";
              data = FormChanges.between(u, data);
              if (!Object.keys(data).length) return;
              const updated = await this.send(
                "/admin/users/" + encodeURIComponent(u.login),
                "PATCH",
                data,
              );
              if (updated.login === this.user?.login) this.user = updated;
            },
          );
        }),
    );
  }
  start() {
    window.addEventListener("hashchange", () => {
      this.resetPage();
      this.commentPage = 0;
      this.commentCursors = [null];
      this.render();
    });
    this.loginView();
  }
}
if (typeof window !== "undefined") new HelpdeskApp().start();

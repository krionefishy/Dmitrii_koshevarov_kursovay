const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const { JSDOM } = require("jsdom");

class UIHarness {
  constructor() {
    this.dom = new JSDOM(
      '<main id="app"></main><dialog id="dialog"></dialog><div id="notice"></div>',
      { url: "http://localhost/#tickets/1", runScripts: "outside-only" },
    );
    this.window = this.dom.window;
    this.window.HTMLDialogElement.prototype.close = function () {
      this.open = false;
    };
    this.window.HTMLDialogElement.prototype.showModal = function () {
      this.open = true;
    };
    const context = this.dom.getInternalVMContext();
    vm.runInContext(
      fs.readFileSync("backend/app/ui/app.js", "utf8") +
        "\nglobalThis.appUnderTest = new HelpdeskApp();",
      context,
    );
    this.app = this.window.appUnderTest;
    this.app.user = {
      login: "support",
      role: "support",
      display_name: "Поддержка",
    };
    this.app.token = "current";
    this.app.notice = (message) => {
      this.notice = message;
    };
    this.ticket = {
      id: 1,
      title: "Тема",
      body: "Описание",
      status: "new",
      author_login: "customer",
      author_name: "Клиент",
      category: { name: "Категория" },
      created_at: "2026-09-01T12:00:00Z",
      reaction: { norm_seconds: 3600, elapsed_seconds: 10, breached: false },
    };
    this.calls = [];
    this.app.api = async (path) =>
      path.includes("/comments?")
        ? { items: [], has_more: true, next_cursor: "older" }
        : structuredClone(this.ticket);
    this.app.send = async (path, method, data) => {
      this.calls.push({ path, method, data });
      if (path.endsWith("/status")) this.ticket.status = data.status;
      return { id: 1 };
    };
  }
  $(selector) {
    return this.window.document.querySelector(selector);
  }
  async render() {
    await this.app.render();
  }
  type(text) {
    const input = this.$("#reply-body");
    input.value = text;
    input.dispatchEvent(new this.window.Event("input"));
  }
  async status() {
    await this.$("#change-status").onclick({
      currentTarget: this.$("#change-status"),
    });
  }
  close() {
    this.window.close();
  }
}

test("draft survives status change and comment pagination; closing requires resolving draft", async () => {
  const h = new UIHarness();
  try {
    await h.render();
    h.type("Неотправленный ответ");
    await h.status();
    assert.equal(h.$("#reply-body").value, "Неотправленный ответ");
    h.$("#comments-prev").onclick();
    await h.render();
    assert.equal(h.$("#reply-body").value, "Неотправленный ответ");
    await h.status();
    assert.equal(h.calls.length, 1);
    assert.equal(h.ticket.status, "in_progress");
    assert.match(h.notice, /черновик/);
    h.type("");
    await h.status();
    assert.equal(h.ticket.status, "closed");
  } finally {
    h.close();
  }
});

test("a remotely closed ticket still exposes an unsent draft for copying", async () => {
  const h = new UIHarness();
  try {
    await h.render();
    h.type("Сохранить текст");
    h.ticket.status = "closed";
    await h.render();
    assert.equal(h.$("#reply-body").value, "Сохранить текст");
    assert.equal(h.$("#reply-body").readOnly, true);
  } finally {
    h.close();
  }
});

test("successful send clears only the submitted draft", async () => {
  const h = new UIHarness();
  try {
    await h.render();
    h.type("Отправляем");
    const form = h.$("#reply-form");
    await form.onsubmit({ preventDefault() {}, currentTarget: form });
    assert.equal(h.$("#reply-body").value, "");
    h.type("Первый");
    let resolve;
    h.app.send = () =>
      new Promise((r) => {
        resolve = r;
      });
    const next = h.$("#reply-form");
    const pending = next.onsubmit({ preventDefault() {}, currentTarget: next });
    h.type("Новый черновик");
    resolve({ id: 2 });
    await pending;
    assert.equal(h.$("#reply-body").value, "Новый черновик");
  } finally {
    h.close();
  }
});

test("stale category form submits only changed fields and no-op saves send nothing", async () => {
  const h = new UIHarness();
  try {
    h.app.user.role = "admin";
    const category = {
      id: 1,
      name: "Категория",
      description: "Было",
      is_active: true,
    };
    h.app.api = async () => ({ items: [category], next_cursor: null });
    h.app.allPages = async () => [{ category_id: 1, response_seconds: 60 }];
    h.app.shell("admin/categories");
    await h.app.categoriesView((html) => {
      h.$("#content").innerHTML = html;
      return true;
    });
    let save;
    h.app.modal = (title, fields, action) => {
      save = action;
    };
    h.$("[data-category]").onclick();
    await save({ name: "Категория", description: "Стало", is_active: "true" });
    assert.deepEqual(JSON.parse(JSON.stringify(h.calls[0].data)), {
      description: "Стало",
    });
    await save({ name: "Категория", description: "Было", is_active: "true" });
    assert.equal(h.calls.length, 1);
  } finally {
    h.close();
  }
});

test("late 401 from a previous session cannot log out a new user", async () => {
  const h = new UIHarness();
  try {
    delete h.app.api;
    let resolve;
    h.window.fetch = () =>
      new Promise((r) => {
        resolve = r;
      });
    h.app.token = "old";
    const pending = h.app.api("/tickets");
    h.app.token = "new";
    resolve({
      ok: false,
      status: 401,
      json: async () => ({ detail: "Expired" }),
    });
    await assert.rejects(pending, /Expired/);
    assert.equal(h.app.token, "new");
    assert.ok(h.app.user);
  } finally {
    h.close();
  }
});

test("logout discards account drafts", async () => {
  const h = new UIHarness();
  try {
    await h.render();
    h.type("Личный текст");
    h.$("#logout").onclick();
    assert.equal(h.app.drafts.size, 0);
    assert.equal(h.app.user, null);
  } finally {
    h.close();
  }
});

test("independent application instances do not share state; output escapes markup", () => {
  const h = new UIHarness();
  try {
    assert.equal(
      h.app.esc("<img src=x onerror=alert(1)>"),
      "&lt;img src=x onerror=alert(1)&gt;",
    );
    assert.equal(h.app.duration(3601), "1 ч 1 с");
    assert.match(h.app.duration(0.000001), /0,000001/);
  } finally {
    h.close();
  }
});

test("late comment completion preserves pagination in another ticket", async () => {
  const h = new UIHarness();
  try {
    await h.render();
    h.type("Ответ");
    let resolve;
    h.app.send = () =>
      new Promise((r) => {
        resolve = r;
      });
    const form = h.$("#reply-form");
    const pending = form.onsubmit({ preventDefault() {}, currentTarget: form });
    h.dom.reconfigure({ url: "http://localhost/#tickets/2" });
    h.app.commentPage = 2;
    h.app.commentCursors = [null, "page2", "page3"];
    resolve({ id: 4 });
    await pending;
    assert.equal(h.app.commentPage, 2);
    assert.equal(h.app.commentCursors[2], "page3");
  } finally {
    h.close();
  }
});

test("late save cannot close a newly opened modal", async () => {
  const h = new UIHarness();
  try {
    let resolve;
    h.app.modal(
      "Старая форма",
      '<input name="name" value="old">',
      () =>
        new Promise((r) => {
          resolve = r;
        }),
    );
    const form = h.$("#dialog form");
    const pending = form.onsubmit({ preventDefault() {}, currentTarget: form });
    h.$("#dialog").close();
    h.app.modal(
      "Новая форма",
      '<input name="name" value="new">',
      async () => {},
    );
    resolve();
    await pending;
    assert.equal(h.$("#dialog").open, true);
    assert.equal(h.$("#dialog h2").textContent, "Новая форма");
  } finally {
    h.close();
  }
});

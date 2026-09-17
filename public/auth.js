(function () {
  const state = {
    mode: "login",
    installedForm: null,
  };

  function textOf(node) {
    return (node && node.textContent ? node.textContent : "").trim();
  }

  function isLoginRoute() {
    return !window.location.pathname || window.location.pathname === "/" || window.location.pathname.includes("login");
  }

  function findAuthForm() {
    const passwordInput = document.querySelector('input[type="password"]');
    if (!passwordInput) return null;
    return passwordInput.closest("form") || passwordInput.parentElement;
  }

  function findSubmitButton(form) {
    const buttons = Array.from(form.querySelectorAll("button"));
    return (
      buttons.find((button) => button.type === "submit") ||
      buttons.find((button) => /login|sign|continue|登录|继续/i.test(textOf(button))) ||
      buttons[buttons.length - 1]
    );
  }

  function findPasswordInput(form) {
    return form.querySelector('input[type="password"]:not([data-plus-confirm-password])');
  }

  function setButtonText(button, value) {
    if (!button) return;
    const textNode = Array.from(button.childNodes).find((node) => node.nodeType === Node.TEXT_NODE);
    if (textNode) {
      textNode.textContent = value;
    } else {
      button.textContent = value;
    }
  }

  function removeNativeError(confirmInput) {
    confirmInput.setCustomValidity("");
  }

  function ensureRegisterControls(form) {
    if (!form || form.dataset.plusAuthEnhanced === "true") return;

    const passwordInput = findPasswordInput(form);
    const submitButton = findSubmitButton(form);
    if (!passwordInput || !submitButton) return;

    form.dataset.plusAuthEnhanced = "true";
    state.installedForm = form;

    const intro = document.createElement("div");
    intro.className = "plus-auth-intro";
    intro.textContent = "没有账号时请选择注册账号，首次提交会在本机创建账号。";

    const switcher = document.createElement("div");
    switcher.className = "plus-auth-switcher";

    const loginButton = document.createElement("button");
    loginButton.type = "button";
    loginButton.className = "plus-auth-tab is-active";
    loginButton.textContent = "登录";

    const registerButton = document.createElement("button");
    registerButton.type = "button";
    registerButton.className = "plus-auth-tab";
    registerButton.textContent = "注册账号";

    switcher.append(loginButton, registerButton);

    const confirmWrap = document.createElement("label");
    confirmWrap.className = "plus-auth-confirm";
    confirmWrap.innerHTML = '<span>确认密码</span><input data-plus-confirm-password="true" type="password" autocomplete="new-password" placeholder="再次输入密码" />';
    const confirmInput = confirmWrap.querySelector("input");

    const note = document.createElement("div");
    note.className = "plus-auth-note";

    form.prepend(switcher);
    form.prepend(intro);
    passwordInput.closest("label, div")?.after(confirmWrap);
    submitButton.before(note);

    function render() {
      const registering = state.mode === "register";
      loginButton.classList.toggle("is-active", !registering);
      registerButton.classList.toggle("is-active", registering);
      confirmWrap.classList.toggle("is-visible", registering);
      confirmInput.required = registering;
      if (!registering) removeNativeError(confirmInput);
      setButtonText(submitButton, registering ? "注册并登录" : "登录");
      note.textContent = registering
        ? "账号和密码会保存在当前电脑的本地 Chainlit 数据库中。"
        : "已有账号请直接登录；首次使用请先切换到注册账号。";
    }

    loginButton.addEventListener("click", () => {
      state.mode = "login";
      render();
    });

    registerButton.addEventListener("click", () => {
      state.mode = "register";
      render();
      confirmInput.focus();
    });

    form.addEventListener(
      "submit",
      (event) => {
        if (state.mode !== "register") return;
        removeNativeError(confirmInput);
        if (passwordInput.value !== confirmInput.value) {
          event.preventDefault();
          event.stopPropagation();
          confirmInput.setCustomValidity("两次输入的密码不一致");
          confirmInput.reportValidity();
        }
      },
      true
    );

    render();
  }

  function enhanceAuthPage() {
    if (!isLoginRoute()) return;
    ensureRegisterControls(findAuthForm());
  }

  const observer = new MutationObserver(enhanceAuthPage);
  observer.observe(document.documentElement, { childList: true, subtree: true });

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", enhanceAuthPage);
  } else {
    enhanceAuthPage();
  }
})();

(function () {
  const state = {
    installed: false,
    open: false,
    items: [],
    activeId: "",
    mapView: null,
    rasterLayer: null,
    opacity: 0.72,
    lastLocation: window.location.href,
    newConversation: false,
  };

  const GEOSCENE_CSS = "https://js.geoscene.cn/4.32/geoscene/themes/light/main.css";
  const GEOSCENE_JS = "https://js.geoscene.cn/4.32/";
  let geosceneLoader;

  function isLoginPage() {
    return window.location.pathname.includes("login");
  }

  function textOf(node) {
    return (node && node.textContent ? node.textContent : "").trim();
  }

  function fmtSize(bytes) {
    if (!Number.isFinite(bytes)) return "";
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  }

  function fmtTime(seconds) {
    if (!seconds) return "";
    return new Date(seconds * 1000).toLocaleString();
  }

  function roleText(role) {
    return {
      output: "输出",
      upload_lulc: "上传 LULC",
      upload_driver: "上传驱动",
      upload_constraint: "上传约束",
      file: "文件",
    }[role] || role || "文件";
  }

  function kindText(kind) {
    return { raster: "栅格", table: "CSV", text: "文本" }[kind] || kind || "文件";
  }

  function loadGeoScene() {
    if (window.require) return Promise.resolve(window.require);

    if (!document.querySelector(`link[href="${GEOSCENE_CSS}"]`)) {
      const link = document.createElement("link");
      link.rel = "stylesheet";
      link.href = GEOSCENE_CSS;
      document.head.appendChild(link);
    }

    if (!geosceneLoader) {
      geosceneLoader = new Promise((resolve, reject) => {
        const existing = document.querySelector(`script[src="${GEOSCENE_JS}"]`);
        if (existing) {
          existing.addEventListener("load", () => resolve(window.require), { once: true });
          existing.addEventListener("error", reject, { once: true });
          return;
        }
        const script = document.createElement("script");
        script.src = GEOSCENE_JS;
        script.async = true;
        script.onload = () => resolve(window.require);
        script.onerror = () => reject(new Error("GeoScene SDK failed to load"));
        document.body.appendChild(script);
      });
    }
    return geosceneLoader;
  }

  function requireModules(requireFn, modules) {
    return new Promise((resolve, reject) => {
      try {
        requireFn(modules, (...loaded) => resolve(loaded), reject);
      } catch (error) {
        reject(error);
      }
    });
  }

  function panelRoot() {
    return document.querySelector(".plus-data-panel");
  }

  function currentThreadIdFromUrl() {
    const url = new URL(window.location.href);
    for (const key of ["thread_id", "threadId", "thread", "id"]) {
      const value = url.searchParams.get(key);
      if (value) return value;
    }
    const match = url.pathname.match(/\/thread\/([^/?#]+)/i);
    return match ? decodeURIComponent(match[1]) : "";
  }

  function withThreadParam(path) {
    const threadId = currentThreadIdFromUrl();
    if (!threadId) return path;
    const joiner = path.includes("?") ? "&" : "?";
    return `${path}${joiner}thread_id=${encodeURIComponent(threadId)}`;
  }

  function markNewConversation() {
    state.newConversation = true;
    resetDataPanel("已进入新对话，发送第一条消息或上传数据后，这里会显示本会话的数据。");
  }

  function markConversationActiveSoon() {
    if (!state.newConversation) return;
    window.setTimeout(() => {
      state.newConversation = false;
      if (state.open) refreshCatalog();
    }, 1200);
  }

  function resetDataPanel(message) {
    clearMap();
    state.items = [];
    state.activeId = "";
    const count = document.querySelector(".plus-data-count");
    const list = document.querySelector(".plus-data-list");
    const detail = document.querySelector(".plus-data-detail");
    if (count) count.textContent = "0 个数据";
    if (list) list.innerHTML = `<div class="plus-data-empty">${escapeHtml(message || "当前会话暂未产生可预览的数据。")}</div>`;
    if (detail) detail.innerHTML = '<div class="plus-data-empty">选择左侧数据查看详情。</div>';
  }

  function clearMap() {
    if (state.mapView) {
      state.mapView.destroy();
      state.mapView = null;
    }
    state.rasterLayer = null;
  }

  async function refreshCatalog() {
    const list = document.querySelector(".plus-data-list");
    if (state.newConversation && !currentThreadIdFromUrl()) {
      resetDataPanel("当前是新的空对话，发送第一条消息或上传数据后，这里会显示本会话的数据。");
      return;
    }
    if (list) list.innerHTML = '<div class="plus-data-empty">正在读取数据列表...</div>';
    try {
      const response = await fetch(withThreadParam("/plus/data-catalog"), { credentials: "include" });
      if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
      const data = await response.json();
      state.items = Array.isArray(data.items) ? data.items : [];
      if (!data.threadId) {
        resetDataPanel("当前是新的空对话，发送第一条消息或上传数据后，这里会显示本会话的数据。");
        return;
      }
      renderList();
    } catch (error) {
      if (list) {
        list.innerHTML = `<div class="plus-data-empty">读取失败：${escapeHtml(error.message || String(error))}</div>`;
      }
    }
  }

  function escapeHtml(value) {
    return String(value)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;");
  }

  function renderList() {
    const list = document.querySelector(".plus-data-list");
    const count = document.querySelector(".plus-data-count");
    if (!list) return;
    if (count) count.textContent = `${state.items.length} 个数据`;
    if (!state.items.length) {
      list.innerHTML = '<div class="plus-data-empty">当前会话还没有可预览的上传或输出数据。</div>';
      return;
    }

    const grouped = new Map();
    for (const item of state.items) {
      const key = item.threadName || item.threadId || "default";
      if (!grouped.has(key)) grouped.set(key, []);
      grouped.get(key).push(item);
    }

    list.innerHTML = "";
    for (const [group, items] of grouped.entries()) {
      const title = document.createElement("div");
      title.className = "plus-data-group";
      title.textContent = group === "default" ? "默认会话" : group;
      list.appendChild(title);
      for (const item of items) {
        const button = document.createElement("button");
        button.type = "button";
        button.className = `plus-data-item${item.id === state.activeId ? " is-active" : ""}`;
        button.innerHTML = `
          <span class="plus-data-item-name">${escapeHtml(item.name)}</span>
          <span class="plus-data-item-meta">${escapeHtml(kindText(item.kind))} · ${escapeHtml(roleText(item.role))} · ${escapeHtml(fmtSize(item.size))}</span>
        `;
        button.addEventListener("click", () => openPreview(item));
        list.appendChild(button);
      }
    }
  }

  async function openPreview(item) {
    state.activeId = item.id;
    renderList();
    const detail = document.querySelector(".plus-data-detail");
    if (!detail) return;
    clearMap();
    detail.innerHTML = `
      <div class="plus-data-detail-head">
        <div>
          <div class="plus-data-detail-title">${escapeHtml(item.name)}</div>
          <div class="plus-data-detail-meta">${escapeHtml(kindText(item.kind))} · ${escapeHtml(roleText(item.role))} · ${escapeHtml(fmtSize(item.size))} · ${escapeHtml(fmtTime(item.modified))}</div>
        </div>
      </div>
      <div class="plus-data-loading">正在生成预览...</div>
    `;

    try {
      const response = await fetch(withThreadParam(`/plus/data-preview/${encodeURIComponent(item.id)}`), { credentials: "include" });
      if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
      const preview = await response.json();
      if (preview.kind === "raster") renderRasterPreview(detail, preview);
      else if (preview.kind === "table") renderTablePreview(detail, preview);
      else renderTextPreview(detail, preview);
    } catch (error) {
      detail.innerHTML += `<div class="plus-data-error">预览失败：${escapeHtml(error.message || String(error))}</div>`;
    }
  }

  function renderTextPreview(detail, preview) {
    detail.innerHTML = `
      <div class="plus-data-detail-head">
        <div class="plus-data-detail-title">${escapeHtml(preview.name)}</div>
      </div>
      <pre class="plus-data-text">${escapeHtml(preview.content || "")}</pre>
    `;
  }

  function renderTablePreview(detail, preview) {
    const stats = Array.isArray(preview.stats) && preview.stats.length
      ? `<div class="plus-data-stats">${preview.stats.map((s) => `
          <div class="plus-data-stat">
            <strong>${escapeHtml(s.name)}</strong>
            <span>min ${escapeHtml(s.min)}</span>
            <span>mean ${escapeHtml(s.mean)}</span>
            <span>max ${escapeHtml(s.max)}</span>
          </div>
        `).join("")}</div>`
      : "";
    const columns = Array.isArray(preview.columns) ? preview.columns : [];
    const rows = Array.isArray(preview.rows) ? preview.rows : [];
    detail.innerHTML = `
      <div class="plus-data-detail-head">
        <div>
          <div class="plus-data-detail-title">${escapeHtml(preview.name)}</div>
          <div class="plus-data-detail-meta">${preview.rowCount} 行 · ${preview.columnCount} 列 · 预览前 ${rows.length} 行</div>
        </div>
      </div>
      ${stats}
      <div class="plus-data-table-wrap">
        <table class="plus-data-table">
          <thead><tr>${columns.map((c) => `<th>${escapeHtml(c)}</th>`).join("")}</tr></thead>
          <tbody>
            ${rows.map((row) => `<tr>${columns.map((_, i) => `<td>${escapeHtml(row[i] ?? "")}</td>`).join("")}</tr>`).join("")}
          </tbody>
        </table>
      </div>
    `;
  }

  async function renderRasterPreview(detail, preview) {
    const props = preview.props || {};
    state.opacity = props.opacity ?? 0.72;
    const stats = props.stats || {};
    const sizeText = Array.isArray(props.rasterSize) ? `${props.rasterSize[0]} x ${props.rasterSize[1]}` : "";
    detail.innerHTML = `
      <div class="plus-data-detail-head">
        <div>
          <div class="plus-data-detail-title">${escapeHtml(preview.name || props.title || "Raster")}</div>
          <div class="plus-data-detail-meta">${props.renderer === "categorical" ? `${stats.classCount ?? "-"} 类` : `${stats.min?.toPrecision?.(4) ?? "-"} - ${stats.max?.toPrecision?.(4) ?? "-"}`} · ${escapeHtml(sizeText)}</div>
        </div>
        <label class="plus-data-opacity">
          <span>${Math.round(state.opacity * 100)}%</span>
          <input type="range" min="0" max="1" step="0.05" value="${state.opacity}" />
        </label>
      </div>
      <div class="plus-data-map"></div>
      ${renderLegend(props.legend)}
    `;
    const input = detail.querySelector(".plus-data-opacity input");
    input?.addEventListener("input", (event) => {
      state.opacity = Number(event.target.value);
      const label = detail.querySelector(".plus-data-opacity span");
      if (label) label.textContent = `${Math.round(state.opacity * 100)}%`;
      if (state.rasterLayer) state.rasterLayer.opacity = state.opacity;
    });
    await createMap(detail.querySelector(".plus-data-map"), props);
  }

  function renderLegend(legend) {
    if (!Array.isArray(legend) || !legend.length) return "";
    return `
      <div class="plus-data-legend">
        ${legend.slice(0, 16).map((item) => `
          <div class="plus-data-legend-item">
            <span class="plus-data-swatch" style="background:${escapeHtml(item.color)}"></span>
            <span>${escapeHtml(item.label)}</span>
          </div>
        `).join("")}
      </div>
    `;
  }

  async function createMap(container, props) {
    if (!container || !props.imageUrl || !props.bounds) return;
    try {
      const requireFn = await loadGeoScene();
      const [
        GeoSceneMap,
        MapView,
        MediaLayer,
        ImageElement,
        ExtentAndRotationGeoreference,
        Extent,
        Expand,
        LayerList,
      ] = await requireModules(requireFn, [
        "geoscene/Map",
        "geoscene/views/MapView",
        "geoscene/layers/MediaLayer",
        "geoscene/layers/support/ImageElement",
        "geoscene/layers/support/ExtentAndRotationGeoreference",
        "geoscene/geometry/Extent",
        "geoscene/widgets/Expand",
        "geoscene/widgets/LayerList",
      ]);

      const extent = new Extent({
        xmin: props.bounds.xmin,
        ymin: props.bounds.ymin,
        xmax: props.bounds.xmax,
        ymax: props.bounds.ymax,
        spatialReference: { wkid: props.bounds.wkid || 4326 },
      });
      const imageElement = new ImageElement({
        image: props.imageUrl,
        georeference: new ExtentAndRotationGeoreference({ extent }),
      });
      const rasterLayer = new MediaLayer({
        title: props.title || props.sourceName || "Raster",
        source: [imageElement],
        opacity: state.opacity,
      });
      const map = new GeoSceneMap({ basemap: "osm", layers: [rasterLayer] });
      const view = new MapView({
        container,
        map,
        extent,
        constraints: { snapToZoom: false },
        popup: { dockEnabled: true },
      });
      state.mapView = view;
      state.rasterLayer = rasterLayer;
      view.when(() => {
        view.goTo(extent.expand(1.08)).catch(() => {});
        const layerList = new LayerList({ view });
        view.ui.add(new Expand({ view, content: layerList, expanded: false }), "top-right");
      });
    } catch (error) {
      container.innerHTML = `
        <div class="plus-data-map-fallback">
          <img src="${escapeHtml(props.imageUrl)}" alt="${escapeHtml(props.title || "Raster preview")}" />
          <div>GeoScene 地图加载失败：${escapeHtml(error.message || String(error))}</div>
        </div>
      `;
    }
  }

  function setOpen(open) {
    state.open = open;
    document.body.classList.toggle("plus-data-open", open);
    if (open) refreshCatalog();
  }

  function detectRouteChange() {
    if (state.lastLocation === window.location.href) return;
    state.lastLocation = window.location.href;
    if (currentThreadIdFromUrl()) state.newConversation = false;
    resetDataPanel("已切换会话，打开或刷新数据栏后只显示当前会话的数据。");
    if (state.open) refreshCatalog();
  }

  function patchHistory() {
    if (window.__plusDataHistoryPatched) return;
    window.__plusDataHistoryPatched = true;
    for (const method of ["pushState", "replaceState"]) {
      const original = history[method];
      history[method] = function () {
        const result = original.apply(this, arguments);
        window.dispatchEvent(new Event("plus-route-change"));
        return result;
      };
    }
    window.addEventListener("popstate", () => window.dispatchEvent(new Event("plus-route-change")));
    window.addEventListener("plus-route-change", detectRouteChange);
    setInterval(detectRouteChange, 1200);
    document.addEventListener("click", (event) => {
      const control = event.target.closest?.("button, a");
      if (!control) return;
      const label = `${control.getAttribute("aria-label") || ""} ${control.getAttribute("title") || ""} ${textOf(control)}`;
      if (/new chat|new thread|新建|新对话|新聊天/i.test(label)) {
        markNewConversation();
        return;
      }
      if (/send|发送/i.test(label)) markConversationActiveSoon();
    }, true);
    document.addEventListener("keydown", (event) => {
      if (event.key !== "Enter" || event.shiftKey || event.ctrlKey || event.altKey || event.metaKey) return;
      const target = event.target;
      if (target?.matches?.("textarea, [contenteditable='true']")) markConversationActiveSoon();
    }, true);
  }

  function installPanel() {
    if (state.installed || isLoginPage()) return;
    state.installed = true;
    patchHistory();

    const button = document.createElement("button");
    button.type = "button";
    button.className = "plus-data-fab";
    button.title = "打开数据面板";
    button.textContent = "数据";
    button.addEventListener("click", () => setOpen(!state.open));

    const panel = document.createElement("aside");
    panel.className = "plus-data-panel";
    panel.innerHTML = `
      <div class="plus-data-header">
        <div>
          <div class="plus-data-title">数据浏览</div>
          <div class="plus-data-count">0 个数据</div>
        </div>
        <div class="plus-data-actions">
          <button type="button" class="plus-data-refresh" title="刷新列表">刷新</button>
          <button type="button" class="plus-data-close" title="收起">收起</button>
        </div>
      </div>
      <div class="plus-data-body">
        <nav class="plus-data-list"></nav>
        <section class="plus-data-detail">
          <div class="plus-data-empty">选择左侧数据查看详情。</div>
        </section>
      </div>
    `;

    panel.querySelector(".plus-data-close").addEventListener("click", () => setOpen(false));
    panel.querySelector(".plus-data-refresh").addEventListener("click", refreshCatalog);
    document.body.append(button, panel);
  }

  const observer = new MutationObserver(installPanel);
  observer.observe(document.documentElement, { childList: true, subtree: true });
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", installPanel);
  } else {
    installPanel();
  }
})();

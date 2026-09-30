(() => {
  const tg = window.Telegram && window.Telegram.WebApp;
  if (tg) {
    try {
      tg.ready();
      tg.expand();
      if (tg.setHeaderColor) tg.setHeaderColor("#0b0614");
      if (tg.setBackgroundColor) tg.setBackgroundColor("#0b0614");
    } catch (_) {}
  }

  const state = {
    me: null,
    playingId: null,
    playCounted: new Set(),
  };

  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

  function initDataHeader() {
    const raw = (tg && tg.initData) || "";
    return raw ? { "X-Telegram-Init-Data": raw } : {};
  }

  async function api(path, opts = {}) {
    const headers = {
      Accept: "application/json",
      ...initDataHeader(),
      ...(opts.headers || {}),
    };
    if (opts.body && !(opts.body instanceof FormData)) {
      headers["Content-Type"] = "application/json";
    }
    const res = await fetch(path, { ...opts, headers });
    let data = null;
    const ct = res.headers.get("content-type") || "";
    if (ct.includes("application/json")) {
      data = await res.json();
    } else {
      data = await res.text();
    }
    if (!res.ok) {
      const detail = (data && data.detail) || data || res.statusText;
      throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
    }
    return data;
  }

  function toast(msg) {
    const el = document.createElement("div");
    el.className = "toast";
    el.textContent = msg;
    document.body.appendChild(el);
    setTimeout(() => el.remove(), 2800);
  }

  function fmtDur(sec) {
    sec = Math.max(0, Math.floor(Number(sec) || 0));
    const m = Math.floor(sec / 60);
    const s = sec % 60;
    return `${m}:${String(s).padStart(2, "0")}`;
  }

  function fmtNum(n) {
    n = Number(n) || 0;
    if (n >= 1000000) return (n / 1000000).toFixed(1).replace(/\.0$/, "") + "M";
    if (n >= 1000) return (n / 1000).toFixed(1).replace(/\.0$/, "") + "K";
    return String(n);
  }

  function badgeFor(t) {
    if (t.source_type === "youtube") return "YT";
    if (t.source_type === "mp3") return "MP3";
    return "AUDIO";
  }

  function thumbHtml(t) {
    const badge = badgeFor(t);
    const dur = fmtDur(t.duration_sec);
    if (t.thumbnail_url) {
      return `<div class="thumb"><img src="${escAttr(t.thumbnail_url)}" alt="" loading="lazy"/><span class="badge">${badge}</span><span class="dur">${dur}</span></div>`;
    }
    return `<div class="thumb">♪<span class="badge">${badge}</span><span class="dur">${dur}</span></div>`;
  }

  function esc(s) {
    return String(s ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }
  function escAttr(s) {
    return esc(s).replace(/'/g, "&#39;");
  }

  function trackCard(t, { editor = false } = {}) {
    const liked = t.liked_by_me ? "liked" : "";
    const heart = t.liked_by_me ? "♥" : "♡";
    let actions = `
      <button type="button" class="play-btn" data-play="${t.id}">▶</button>
      <button type="button" class="like-btn ${liked}" data-like="${t.id}">${heart} ${fmtNum(t.likes_count)}</button>
    `;
    if (editor) {
      actions += `
        <button type="button" class="edit-btn" data-edit="${t.id}">✎</button>
        <button type="button" class="del-btn" data-del="${t.id}">🗑</button>
      `;
    }
    return `
      <article class="track-card" data-id="${t.id}">
        ${thumbHtml(t)}
        <div class="t-body">
          <div class="t-title">${esc(t.title)}</div>
          <div class="t-artist">${esc(t.artist || "Невідомий виконавець")}</div>
          <div class="t-meta">
            <span>♥ ${fmtNum(t.likes_count)}</span>
            <span>▶ ${fmtNum(t.plays_count)}</span>
          </div>
        </div>
        <div class="t-actions">${actions}</div>
      </article>
    `;
  }

  function renderList(el, tracks, opts) {
    if (!tracks.length) {
      el.innerHTML = "";
      return;
    }
    el.innerHTML = tracks.map((t) => trackCard(t, opts)).join("");
  }

  function showScreen(name) {
    $$(".screen").forEach((s) => s.classList.toggle("active", s.dataset.screen === name));
    $$(".nav-btn").forEach((b) => b.classList.toggle("active", b.dataset.nav === name));
  }

  async function refreshStats() {
    const s = await api("/api/stats");
    const line = `${s.tracks} треков · ${s.playlists} плейлистов · ${fmtNum(s.plays)} прослушиваний`;
    $("#statsLine").textContent = line;
  }

  async function loadHome() {
    const [recent, popular] = await Promise.all([
      api("/api/tracks/recent"),
      api("/api/tracks/popular"),
    ]);
    renderList($("#recentList"), recent);
    $("#recentEmpty").classList.toggle("hidden", recent.length > 0);
    renderList($("#popularList"), popular);
    $("#popularEmpty").classList.toggle("hidden", popular.length > 0);
    await refreshStats();
  }

  async function loadLibrary() {
    const tracks = await api("/api/library");
    renderList($("#libraryList"), tracks);
    $("#libraryEmpty").classList.toggle("hidden", tracks.length > 0);
    const pls = await api("/api/playlists");
    const plEl = $("#playlistList");
    if (!pls.length) {
      plEl.innerHTML = `<p class="empty">Немає плейлистів</p>`;
    } else {
      plEl.innerHTML = pls
        .map(
          (p) =>
            `<div class="playlist-item"><strong>${esc(p.name)}</strong><span>${p.tracks_count} треків</span></div>`
        )
        .join("");
    }
  }

  async function loadEditor() {
    const recent = await api("/api/tracks/recent?limit=50");
    renderList($("#editorList"), recent, { editor: true });
  }

  let searchTimer = null;
  async function doSearch(q) {
    const hint = $("#searchHint");
    if (!q.trim()) {
      $("#searchList").innerHTML = "";
      hint.textContent = "Введіть запит";
      hint.classList.remove("hidden");
      return;
    }
    const tracks = await api(`/api/tracks/search?q=${encodeURIComponent(q)}`);
    renderList($("#searchList"), tracks);
    if (!tracks.length) {
      hint.textContent = "Нічого не знайдено";
      hint.classList.remove("hidden");
    } else {
      hint.classList.add("hidden");
    }
  }

  function streamUrl(t) {
    if (t.stream_url) return t.stream_url;
    return t.source_url;
  }

  async function playTrack(t) {
    const audio = $("#audioEl");
    const url = streamUrl(t);
    if (!url) {
      toast("Немає потоку для відтворення");
      return;
    }
    state.playingId = t.id;
    $("#playerBar").classList.remove("hidden");
    $("#playerTitle").textContent = t.title;
    $("#playerArtist").textContent = t.artist || "—";
    const thumb = $("#playerThumb");
    if (t.thumbnail_url) {
      thumb.innerHTML = `<img src="${escAttr(t.thumbnail_url)}" alt=""/>`;
    } else {
      thumb.textContent = "♪";
    }
    audio.src = url;
    try {
      await audio.play();
      $("#btnPlayPause").textContent = "⏸";
    } catch (e) {
      toast("Не вдалося відтворити");
      console.warn(e);
    }
    if (!state.playCounted.has(t.id)) {
      state.playCounted.add(t.id);
      try {
        await api(`/api/tracks/${t.id}/play`, { method: "POST" });
        refreshStats().catch(() => {});
      } catch (_) {}
    }
  }

  async function onLike(id, btn) {
    try {
      const r = await api(`/api/tracks/${id}/like`, { method: "POST" });
      btn.classList.toggle("liked", r.liked);
      btn.textContent = `${r.liked ? "♥" : "♡"} ${fmtNum(r.likes_count)}`;
      // update meta on card
      const card = btn.closest(".track-card");
      if (card) {
        const meta = card.querySelector(".t-meta span");
        if (meta) meta.textContent = `♥ ${fmtNum(r.likes_count)}`;
      }
    } catch (e) {
      toast(e.message || "Помилка лайку");
    }
  }

  async function findTrack(id) {
    return api(`/api/tracks/${id}`);
  }

  function bindLists() {
    document.body.addEventListener("click", async (ev) => {
      const play = ev.target.closest("[data-play]");
      if (play) {
        try {
          const t = await findTrack(play.dataset.play);
          await playTrack(t);
        } catch (e) {
          toast(e.message);
        }
        return;
      }
      const like = ev.target.closest("[data-like]");
      if (like) {
        onLike(like.dataset.like, like);
        return;
      }
      const edit = ev.target.closest("[data-edit]");
      if (edit) {
        const t = await findTrack(edit.dataset.edit);
        const title = prompt("Назва", t.title);
        if (title === null) return;
        const artist = prompt("Виконавець", t.artist || "");
        if (artist === null) return;
        try {
          await api(`/api/tracks/${t.id}`, {
            method: "PATCH",
            body: JSON.stringify({ title, artist }),
          });
          toast("Збережено");
          loadEditor();
          loadHome();
        } catch (e) {
          toast(e.message);
        }
        return;
      }
      const del = ev.target.closest("[data-del]");
      if (del) {
        if (!confirm("Видалити трек?")) return;
        try {
          await api(`/api/tracks/${del.dataset.del}`, { method: "DELETE" });
          toast("Видалено");
          loadEditor();
          loadHome();
        } catch (e) {
          toast(e.message);
        }
      }
    });
  }

  function bindNav() {
    $$(".nav-btn").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const name = btn.dataset.nav;
        showScreen(name);
        try {
          if (name === "home") await loadHome();
          if (name === "library") await loadLibrary();
        } catch (e) {
          toast(e.message);
        }
      });
    });
  }

  function bindModals() {
    const modal = $("#addModal");
    $("#btnOpenAdd").addEventListener("click", () => {
      $("#addErr").classList.add("hidden");
      modal.classList.remove("hidden");
    });
    $("#btnAddCancel").addEventListener("click", () => modal.classList.add("hidden"));
    modal.addEventListener("click", (e) => {
      if (e.target === modal) modal.classList.add("hidden");
    });
    $("#btnAddSubmit").addEventListener("click", async () => {
      const url = $("#addUrl").value.trim();
      const title = $("#addTitle").value.trim();
      const artist = $("#addArtist").value.trim();
      const err = $("#addErr");
      if (!url) {
        err.textContent = "Вкажіть URL";
        err.classList.remove("hidden");
        return;
      }
      const btn = $("#btnAddSubmit");
      btn.disabled = true;
      btn.textContent = "Завантаження…";
      try {
        const body = { url };
        if (title) body.title = title;
        if (artist) body.artist = artist;
        await api("/api/tracks", { method: "POST", body: JSON.stringify(body) });
        modal.classList.add("hidden");
        $("#addUrl").value = "";
        $("#addTitle").value = "";
        $("#addArtist").value = "";
        toast("Трек додано");
        await loadHome();
      } catch (e) {
        err.textContent = e.message || "Помилка";
        err.classList.remove("hidden");
      } finally {
        btn.disabled = false;
        btn.textContent = "Додати";
      }
    });
  }

  async function boot() {
    const bootEl = $("#bootStatus");
    try {
      const me = await api("/api/me");
      state.me = me;
      $("#greeting").textContent = me.greeting || `Привет, ${me.first_name || "Slim"}`;
      const initials = ((me.first_name || "S")[0] + (me.last_name || "L")[0] || "SL").toUpperCase();
      $("#avatar").textContent = initials.slice(0, 2);
      document.title = me.brand_name || "Slim Music";

      $("#btnClose").addEventListener("click", () => {
        if (tg && tg.close) tg.close();
        else window.close();
      });
      $("#btnReport").addEventListener("click", () => toast("Дякуємо! (stub)"));
      $("#btnEditor").addEventListener("click", async () => {
        if (!me.is_admin) {
          toast("Редактор лише для адміна");
          return;
        }
        showScreen("editor");
        await loadEditor();
      });
      $("#btnCreatePlaylist").addEventListener("click", async () => {
        const name = $("#playlistName").value.trim();
        if (!name) return;
        try {
          await api("/api/playlists", { method: "POST", body: JSON.stringify({ name }) });
          $("#playlistName").value = "";
          await loadLibrary();
          await refreshStats();
          toast("Плейлист створено");
        } catch (e) {
          toast(e.message);
        }
      });
      $("#searchInput").addEventListener("input", (e) => {
        clearTimeout(searchTimer);
        searchTimer = setTimeout(() => doSearch(e.target.value).catch((err) => toast(err.message)), 280);
      });
      $("#btnPlayPause").addEventListener("click", () => {
        const audio = $("#audioEl");
        if (audio.paused) {
          audio.play();
          $("#btnPlayPause").textContent = "⏸";
        } else {
          audio.pause();
          $("#btnPlayPause").textContent = "▶";
        }
      });
      $("#audioEl").addEventListener("ended", () => {
        $("#btnPlayPause").textContent = "▶";
      });

      bindNav();
      bindModals();
      bindLists();
      await loadHome();

      bootEl.classList.add("hidden");
      $("#app").classList.remove("hidden");
    } catch (e) {
      bootEl.textContent = "Помилка: " + (e.message || e);
    }
  }

  boot();
})();

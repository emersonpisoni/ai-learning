// Tela da partida: modo deus, replay e acompanhamento ao vivo (polling).
(() => {
  const body = document.body;
  const live = document.getElementById("live");
  const godToggle = document.getElementById("god-mode");
  const replayBtn = document.getElementById("replay");

  // O conteúdo de #live é substituído durante a partida, então sempre
  // buscamos os elementos na hora em vez de guardar referências.
  const timelineItems = () => [...live.querySelectorAll("#timeline .event, #timeline .round-title")];
  const players = () => new Map([...live.querySelectorAll(".player")].map((el) => [el.dataset.name, el]));
  const isRunning = () => ["running", "created"].includes(live.dataset.status);

  // ----- Modo deus: mostra papéis secretos, eventos privados e pensamentos -----
  const setGodMode = (on) => {
    body.classList.toggle("god-mode", on);
    try { localStorage.setItem("godMode", on ? "1" : "0"); } catch {}
  };
  try { godToggle.checked = localStorage.getItem("godMode") === "1"; } catch {}
  setGodMode(godToggle.checked);
  godToggle.addEventListener("change", () => setGodMode(godToggle.checked));

  // ----- Ao vivo: busca o HTML novo a cada 2s enquanto a partida roda -----
  let lastCount = timelineItems().length;

  const nearBottom = () => window.innerHeight + window.scrollY >= document.body.scrollHeight - 200;

  const poll = async () => {
    try {
      const resp = await fetch(live.dataset.url, { headers: { Accept: "application/json" } });
      const data = await resp.json();
      const stickToBottom = nearBottom();
      live.dataset.status = data.status;
      if (data.events !== lastCount || !isRunning()) {
        live.innerHTML = data.html;
        // Anima só os eventos novos.
        timelineItems().slice(lastCount).forEach((el) => el.classList.add("pop"));
        lastCount = data.events;
        if (stickToBottom) window.scrollTo({ top: document.body.scrollHeight, behavior: "smooth" });
      }
    } catch (err) {
      console.warn("Falha ao atualizar a partida", err);
    }
    if (isRunning()) setTimeout(poll, 2000);
    else replayBtn.disabled = false;
  };

  if (isRunning()) {
    replayBtn.disabled = true;
    setTimeout(poll, 1500);
  }

  // ----- Replay: reproduz a partida evento por evento -----
  let timer = null;

  const resetTable = () => {
    players().forEach((el) => {
      el.classList.remove("dead", "speaking", "targeted");
      el.querySelector(".role").classList.add("secret");
    });
  };

  const highlight = (name, cls) => {
    const el = players().get(name);
    if (!el) return;
    el.classList.add(cls);
    setTimeout(() => el.classList.remove(cls), 900);
  };

  const applyEvent = (el) => {
    const { kind, actor, target } = el.dataset;
    if (kind === "morte" || kind === "eliminacao") {
      const p = players().get(target);
      p?.classList.add("dead");
      p?.querySelector(".role").classList.remove("secret");
    }
    if (kind === "fim_de_jogo") {
      players().forEach((p) => p.querySelector(".role").classList.remove("secret"));
    }
    if (actor) highlight(actor, "speaking");
    if (target && (kind === "voto" || kind === "fala")) highlight(target, "targeted");
  };

  const isVisibleNow = (el) => body.classList.contains("god-mode") || !el.classList.contains("private");

  const stop = () => {
    clearTimeout(timer);
    timer = null;
    replayBtn.textContent = "▶ Reproduzir";
  };

  replayBtn.addEventListener("click", () => {
    const events = timelineItems();
    if (timer) {
      stop();
      events.forEach((el) => el.classList.remove("hidden"));
      return;
    }
    resetTable();
    events.forEach((el) => el.classList.add("hidden"));
    replayBtn.textContent = "⏹ Parar";

    let i = 0;
    const next = () => {
      // Pula eventos privados quando o modo deus está desligado.
      while (i < events.length && !isVisibleNow(events[i])) {
        events[i].classList.remove("hidden");
        if (events[i].dataset.kind) applyEvent(events[i]);
        i++;
      }
      if (i >= events.length) return stop();

      const el = events[i++];
      el.classList.remove("hidden");
      el.classList.add("pop");
      if (el.dataset.kind) applyEvent(el);
      el.scrollIntoView({ behavior: "smooth", block: "center" });

      const delay = el.dataset.kind === "fala" ? 1600 : 650;
      timer = setTimeout(next, delay);
    };
    next();
  });
})();

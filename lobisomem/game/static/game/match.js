// Interações da tela da partida: modo deus e replay evento por evento.
(() => {
  const body = document.body;
  const godToggle = document.getElementById("god-mode");
  const replayBtn = document.getElementById("replay");
  const events = [...document.querySelectorAll("#timeline .event, #timeline .round-title")];
  const players = new Map(
    [...document.querySelectorAll(".player")].map((el) => [el.dataset.name, el])
  );

  // ----- Modo deus: mostra papéis secretos, eventos privados e pensamentos -----
  const setGodMode = (on) => {
    body.classList.toggle("god-mode", on);
    try { localStorage.setItem("godMode", on ? "1" : "0"); } catch {}
  };
  try { godToggle.checked = localStorage.getItem("godMode") === "1"; } catch {}
  setGodMode(godToggle.checked);
  godToggle.addEventListener("change", () => setGodMode(godToggle.checked));

  // ----- Replay -----
  let timer = null;

  const resetTable = () => {
    players.forEach((el) => {
      el.classList.remove("dead", "speaking", "targeted");
      el.querySelector(".role").classList.add("secret");
    });
  };

  const highlight = (name, cls) => {
    const el = players.get(name);
    if (!el) return;
    el.classList.add(cls);
    setTimeout(() => el.classList.remove(cls), 900);
  };

  const applyEvent = (el) => {
    const { kind, actor, target } = el.dataset;
    if (kind === "morte" || kind === "eliminacao") {
      const p = players.get(target);
      p?.classList.add("dead");
      p?.querySelector(".role").classList.remove("secret");
    }
    if (kind === "fim_de_jogo") {
      players.forEach((p) => p.querySelector(".role").classList.remove("secret"));
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
        if (events[i].dataset) applyEvent(events[i]);
        i++;
      }
      if (i >= events.length) return stop();

      const el = events[i++];
      el.classList.remove("hidden");
      el.classList.add("pop");
      if (el.dataset.kind) applyEvent(el);
      el.scrollIntoView({ behavior: "smooth", block: "center" });

      const delay = el.dataset.kind === "fala" ? 1100 : 650;
      timer = setTimeout(next, delay);
    };
    next();
  });
})();

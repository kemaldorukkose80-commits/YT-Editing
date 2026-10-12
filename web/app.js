/* YT-Editing arayüz mantığı */
const $ = (s) => document.querySelector(s);
const $$ = (s) => Array.from(document.querySelectorAll(s));

function toast(msg, ms = 3200) {
  const t = $("#toast");
  t.textContent = msg;
  t.hidden = false;
  clearTimeout(t._h);
  t._h = setTimeout(() => (t.hidden = true), ms);
}

/* ---------------- sekmeler ---------------- */
$$(".tab").forEach((b) =>
  b.addEventListener("click", () => {
    $$(".tab").forEach((x) => x.classList.remove("active"));
    $$(".panel").forEach((x) => x.classList.remove("active"));
    b.classList.add("active");
    $("#tab-" + b.dataset.tab).classList.add("active");
    if (b.dataset.tab === "jobs") refreshJobs();
    if (b.dataset.tab === "settings") loadSettings();
    if (b.dataset.tab === "new") refreshStatus();
  })
);

/* ---------------- durum şeridi ---------------- */
async function refreshStatus() {
  try {
    const s = await (await fetch("/api/status")).json();
    const chips = [];
    chips.push(chip(s.brave_key && (s.net?.brave !== false), "Brave anahtarı" + (s.brave_key ? "" : " yok") + (s.net?.brave === false ? " (bu ortamdan erişilemiyor)" : "")));
    chips.push(chip(s.pexels_key && (s.net?.pexels !== false), "Pexels anahtarı" + (s.pexels_key ? "" : " yok") + (s.net?.pexels === false ? " (bu ortamdan erişilemiyor)" : "")));
    chips.push(chip(s.github_auth, s.github_auth ? "GitHub bağlı: " + (s.repo || "") : "GitHub bağlı DEĞİL"));
    $("#statusStrip").innerHTML = chips.join("");
  } catch (e) { /* sessiz */ }
}
function chip(on, label) {
  return `<span class="chip ${on ? "on" : "off"}">${on ? "✓" : "✕"} ${label}</span>`;
}

/* ---------------- yeni iş ---------------- */
$("#scriptFile").addEventListener("change", async (e) => {
  const f = e.target.files[0];
  if (f) $("#scriptText").value = await f.text();
});

$("#submitBtn").addEventListener("click", () => {
  const audio = $("#audioFile").files[0];
  const script = $("#scriptText").value.trim();
  const msg = $("#submitMsg");
  if (!audio) { toast("Lütfen ses dosyası seç."); return; }
  if (!script) { toast("Lütfen video metnini gir."); return; }
  const mode = document.querySelector('input[name=mode]:checked').value;
  const fd = new FormData();
  fd.append("mode", mode);
  fd.append("title", $("#jobTitle").value || audio.name.replace(/\.[^.]+$/, ""));
  fd.append("script", script);
  fd.append("audio", audio);
  fd.append("overlay_manual", $("#manualOverlays").value);
  fd.append("options", JSON.stringify({
    resolution: $("#optRes").value,
    video_ratio: parseFloat($("#optRatio").value),
    transition: parseFloat($("#optTrans").value),
    overlay_max: parseInt($("#optOv").value),
    language: $("#optLang").value,
  }));

  const btn = $("#submitBtn");
  btn.disabled = true;
  $("#uploadBar").hidden = false;
  const xhr = new XMLHttpRequest();
  xhr.open("POST", "/api/jobs");
  xhr.upload.onprogress = (e) => {
    if (e.lengthComputable) {
      const p = Math.round((e.loaded / e.total) * 100);
      $("#uploadFill").style.width = p + "%";
      $("#uploadText").textContent = `Yükleniyor %${p}`;
    }
  };
  xhr.onload = () => {
    btn.disabled = false;
    try {
      const r = JSON.parse(xhr.responseText);
      if (xhr.status === 200 && r.ok) {
        msg.textContent = mode === "actions"
          ? "İş GitHub'a gönderildi! 📋 İşler sekmesinden takip et."
          : "Test üretimi başladı! 📋 İşler sekmesinden takip et.";
        toast("İş oluşturuldu ✓");
        $("#uploadBar").hidden = true;
        $$(".tab")[1].click();
      } else {
        msg.textContent = r.error || "Hata oluştu.";
        toast(r.error || "Hata", 5000);
      }
    } catch (e) { msg.textContent = "Sunucu hatası: " + xhr.status; }
  };
  xhr.onerror = () => { btn.disabled = false; toast("Yükleme hatası — bağlantıyı kontrol et."); };
  xhr.send(fd);
});

/* ---------------- işler ---------------- */
let jobTimer = null;
function startPolling() {
  clearInterval(jobTimer);
  jobTimer = setInterval(() => {
    if ($("#tab-jobs").classList.contains("active")) refreshJobs();
  }, 2500);
}
startPolling();

async function refreshJobs() {
  try {
    const jobs = await (await fetch("/api/jobs")).json();
    const el = $("#jobsList");
    const active = jobs.filter(j => ["queued", "running"].includes(j.state?.status)).length;
    const badge = $("#jobBadge");
    badge.hidden = active === 0;
    badge.textContent = active;
    if (!jobs.length) { el.innerHTML = '<p class="hint">Henüz iş yok.</p>'; return; }
    el.innerHTML = jobs.map(jobCard).join("");
    // log detayları açık olanları güncelle
    $$(".job pre[data-open]").forEach((pre) => {
      const j = jobs.find((x) => x.id === pre.dataset.job);
      if (j) pre.textContent = j.log || "";
    });
    // actions işlerinde canlı durum için tek tek çek
    jobs.filter(j => j.mode === "actions" && ["queued", "running"].includes(j.state?.status))
        .forEach(async (j) => {
          try {
            const d = await (await fetch("/api/job/" + j.id)).json();
            const card = document.querySelector(`.job[data-id="${j.id}"] .pfill`);
            const det = document.querySelector(`.job[data-id="${j.id}"] .detail`);
            const pill = document.querySelector(`.job[data-id="${j.id}"] .pill`);
            if (det) det.textContent = detailText(d.state);
            if (card) card.style.width = (d.state?.pct || 0) + "%";
            if (pill) { pill.textContent = pillText(d.state); pill.className = "pill " + pillClass(d.state); }
            if (d.state?.status === "done" || d.state?.status === "error") setTimeout(refreshJobs, 800);
          } catch (e) {}
        });
  } catch (e) {}
}

function pillText(st) {
  return ({ queued: "Sırada", running: "Çalışıyor", done: "Tamamlandı", error: "Hata", canceled: "İptal" }[st?.status] || st?.status || "");
}
function pillClass(st) { return st?.status || "queued"; }
function detailText(st) {
  if (!st) return "";
  let s = `${st.stage || ""} %${st.pct || 0} — ${st.detail || ""}`;
  if (st.error) s += ` (${st.error})`;
  return s;
}

function jobCard(j) {
  const st = j.state || {};
  const links = [];
  if (st.status === "done") {
    if (st.output && st.output.startsWith("/download"))
      links.push(`<a class="dl" href="${st.output}">⬇️ MP4 indir</a>`);
    if (st.output && String(st.output).startsWith("http"))
      links.push(`<a class="dl" href="${st.output}" target="_blank">⬇️ GitHub'da indir</a>`);
    if (st.run_url) links.push(`<a href="${st.run_url}" target="_blank">Actions kaydı</a>`);
  } else {
    if (st.run_url) links.push(`<a href="${st.run_url}" target="_blank">Actions kaydı</a>`);
    if (["queued", "running"].includes(st.status))
      links.push(`<button onclick="cancelJob('${j.id}')">İptal</button>`);
  }
  links.push(`<button onclick="delJob('${j.id}')">🗑 Sil</button>`);
  const report = j.id && (j.mode !== "actions") ? `<button onclick="toggleLog(this)" data-job="${j.id}">📜 Log</button>` : `<button onclick="toggleLog(this)" data-job="${j.id}">📜 Log</button>`;
  const preview = st.status === "done" && st.output && st.output.startsWith("/media") ? "" :
    (st.status === "done" && st.output && st.output.startsWith("/download") ? `<video class="preview" controls preload="metadata" src="/media/${j.id}"></video>` : "");
  return `<div class="job" data-id="${j.id}">
    <div class="head">
      <span class="name">${j.title || j.id}</span>
      <span class="pill ${pillClass(st)}">${pillText(st)}</span>
    </div>
    <div class="pbar"><div class="pfill" style="width:${st.pct || 0}%"></div></div>
    <div class="detail">${detailText(st)}</div>
    <div class="actions">${links.join("")}${report}</div>
    ${preview}
    <pre data-job="${j.id}" hidden></pre>
  </div>`;
}

window.toggleLog = (btn) => {
  const pre = btn.closest(".job").querySelector("pre");
  pre.hidden = !pre.hidden;
  if (!pre.hidden) pre.dataset.open = "1";
};
window.cancelJob = async (id) => { await fetch(`/api/job/${id}/cancel`, { method: "POST" }); toast("İptal edildi"); refreshJobs(); };
window.delJob = async (id) => {
  if (!confirm("İş ve çıktısı silinsin mi?")) return;
  await fetch(`/api/job/${id}`, { method: "DELETE" });
  refreshJobs();
};

/* ---------------- ayarlar ---------------- */
async function loadSettings() {
  try {
    const s = await (await fetch("/api/settings")).json();
    $("#setBrave").value = s.brave_key || "";
    $("#setPexels").value = s.pexels_key || "";
    $("#setBranch").value = s.github_branch || "main";
    $("#setRes").value = s.defaults?.resolution || "1080p";
    $("#setRatio").value = String(s.defaults?.video_ratio ?? 0.25);
    $("#setTrans").value = String(s.defaults?.transition ?? 0.35);
    $("#setOv").value = String(s.defaults?.overlay_max ?? 5);
  } catch (e) {}
}
$("#saveSettings").addEventListener("click", async () => {
  const body = {
    brave_key: $("#setBrave").value.trim(),
    pexels_key: $("#setPexels").value.trim(),
    github_branch: $("#setBranch").value.trim() || "main",
    defaults: {
      resolution: $("#setRes").value,
      video_ratio: parseFloat($("#setRatio").value),
      transition: parseFloat($("#setTrans").value),
      overlay_max: parseInt($("#setOv").value),
    },
  };
  await fetch("/api/settings", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  $("#setMsg").textContent = "Kaydedildi ✓ " + new Date().toLocaleTimeString("tr-TR");
  toast("Ayarlar kaydedildi ✓");
  refreshStatus();
});

refreshStatus();

(function () {
  "use strict";
  if (window.IsleVideos) return;

  var MB = 1048576;
  var cfg = {
    maxBytes: 25 * MB,
    maxShrinkSeconds: 180,
    slowMs: 20000,
    t: function (s) { return s; },
    allowUrl: function () { return true; },
    readMeta: null
  };
  var T = function (s, vars) {
    var r; try { r = cfg.t(s); } catch (e) { r = null; }
    r = r || s;
    return vars ? r.replace(/\{(\w+)\}/g, function (_, k) { return vars[k] != null ? vars[k] : ""; }) : r;
  };
  var esc = function (s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]; }); };
  var fmtMB = function (n) { return (n / MB).toFixed(n < 10 * MB ? 1 : 0) + " MB"; };
  var fmtTime = function (s) { s = Math.max(0, Math.round(s)); var m = Math.floor(s / 60), r = s % 60; return m + ":" + (r < 10 ? "0" : "") + r; };
  var codeErr = function (code, extra) { var e = new Error(code); e.code = code; if (extra) e.extra = extra; return e; };

  var css = [
    ".vplayer{position:relative;width:100%;aspect-ratio:16/9;max-height:360px;border-radius:12px;background:linear-gradient(135deg,var(--vp-a,#0b2f3d),var(--vp-b,#145c4a));overflow:hidden;display:flex;align-items:center;justify-content:center}",
    ".vplayer.live,.vplayer.failed{aspect-ratio:auto}",
    ".vplayer.live{background:#000}",
    ".vplayer.failed{background:none;overflow:visible}",
    ".vplay{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:.5rem;width:100%;height:100%;min-height:150px;border:0;background:transparent;color:#fff;font:700 1rem var(--body,system-ui,sans-serif);cursor:pointer}",
    ".vplay:focus-visible{outline:3px solid var(--sun,#f8b933);outline-offset:-4px}",
    ".vicon{display:grid;place-items:center;width:3.6rem;height:3.6rem;border-radius:50%;background:var(--play-bg,rgba(255,255,255,.92));color:var(--vp-a,#0b2f3d);font-size:1.5rem;padding-left:.2rem;transition:transform .15s}",
    ".vplay:hover .vicon{transform:scale(1.08)}",
    ".vplayer video{width:100%;max-height:360px;display:block;background:#000}",
    ".vplayer.loading::after{content:\"\";position:absolute;width:2.4rem;height:2.4rem;border:4px solid rgba(255,255,255,.35);border-top-color:#fff;border-radius:50%;animation:vspin .9s linear infinite;pointer-events:none}",
    "@keyframes vspin{to{transform:rotate(360deg)}}",
    "@media (prefers-reduced-motion:reduce){.vplayer.loading::after{animation-duration:3s}.vicon{transition:none}}",
    ".verr{width:100%;padding:.9rem 1rem;background:#fff3f0;color:#5a1d12;border:1px solid #f0c4ba;border-radius:12px;font-size:.93rem}",
    ".verr p{margin:.25rem 0}",
    ".verr button,.vnote button{background:none;border:0;padding:0;font:700 .92rem var(--body,system-ui,sans-serif);color:var(--palm-d,#14603f);text-decoration:underline;cursor:pointer}",
    ".verr a{color:var(--palm-d,#14603f);font-weight:700}",
    ".vnote{margin:.4rem 0 0;font-size:.9rem;line-height:1.4;color:var(--muted,#51636b)}",
    ".vnote.ok{color:#14603f}",
    ".vnote.err{color:#8a1c0e}",
    ".vnote progress{display:block;width:100%;height:.7rem;margin:.35rem 0}"
  ].join("\n");
  var styleEl = document.createElement("style"); styleEl.id = "isle-videos-css"; styleEl.textContent = css;
  (document.head || document.documentElement).appendChild(styleEl);

  var OK_TYPES = ["video/mp4", "video/webm", "video/quicktime"];
  var EXT_TYPES = { mp4: "video/mp4", m4v: "video/mp4", webm: "video/webm", mov: "video/quicktime", qt: "video/quicktime" };
  var ALIASES = { "video/x-m4v": "video/mp4", "video/mov": "video/quicktime", "video/x-quicktime": "video/quicktime" };
  function typeOf(f) {
    var t = String((f && f.type) || "").toLowerCase().split(";")[0];
    if (ALIASES[t]) return ALIASES[t];
    if (OK_TYPES.indexOf(t) >= 0) return t;
    if (!t || t === "application/octet-stream") { var m = /\.([a-z0-9]+)$/i.exec((f && f.name) || ""); if (m && EXT_TYPES[m[1].toLowerCase()]) return EXT_TYPES[m[1].toLowerCase()]; }
    return t;
  }
  function normalize(f) {
    var t = typeOf(f);
    if (!f || OK_TYPES.indexOf(t) < 0 || t === f.type) return f;
    try { return new File([f], f.name, { type: t, lastModified: f.lastModified }); } catch (e) { return f; }
  }

  function readMeta(file, timeout) {
    if (cfg.readMeta) return Promise.resolve(cfg.readMeta(file));
    return new Promise(function (resolve) {
      var v = document.createElement("video"), url = URL.createObjectURL(file), done = false, tm;
      v.preload = "metadata"; v.muted = true; v.playsInline = true;
      var fin = function (r) {
        if (done) return; done = true; clearTimeout(tm);
        v.onloadedmetadata = v.onerror = v.ontimeupdate = null;
        try { v.removeAttribute("src"); v.load(); } catch (e) {}
        URL.revokeObjectURL(url); resolve(r);
      };
      tm = setTimeout(function () { fin("unknown"); }, timeout || 10000);
      v.onerror = function () { fin(null); };
      v.onloadedmetadata = function () {
        if (!(v.videoWidth > 0)) return fin(null);
        if (isFinite(v.duration)) return fin({ duration: v.duration, width: v.videoWidth, height: v.videoHeight });
        v.ontimeupdate = function () { if (isFinite(v.duration)) fin({ duration: v.duration, width: v.videoWidth, height: v.videoHeight }); };
        try { v.currentTime = 1e101; } catch (e) { fin("unknown"); }
      };
      v.src = url;
    });
  }
  function inspect(file) {
    var type = typeOf(file), out = { ok: false, name: file.name, size: file.size, type: type, tooBig: file.size > cfg.maxBytes };
    if (OK_TYPES.indexOf(type) < 0) { out.problem = "type"; return Promise.resolve(out); }
    return readMeta(file).then(function (m) {
      if (m === null) { out.problem = "unplayable"; return out; }
      out.ok = true;
      if (m === "unknown") { out.unknown = true; return out; }
      out.duration = m.duration; out.width = m.width; out.height = m.height; return out;
    });
  }

  function recorderMime() {
    if (typeof MediaRecorder === "undefined" || !MediaRecorder.isTypeSupported) return "";
    var list = ["video/webm;codecs=vp9,opus", "video/webm;codecs=vp8,opus", "video/webm", "video/mp4"];
    for (var i = 0; i < list.length; i++) if (MediaRecorder.isTypeSupported(list[i])) return list[i];
    return "";
  }
  function canShrink() {
    return !!(recorderMime() && window.HTMLCanvasElement && HTMLCanvasElement.prototype.captureStream && (window.AudioContext || window.webkitAudioContext));
  }
  function record(file, p) {
    return new Promise(function (resolve, reject) {
      var v = document.createElement("video"), url = URL.createObjectURL(file), canvas = document.createElement("canvas");
      canvas.width = p.w; canvas.height = p.h;
      var g = canvas.getContext("2d", { alpha: false }), fps = 30, chunks = [], aborted = false, finished = false, timer = null, lastTick = Date.now(), watchdog = null;
      v.playsInline = true; v.preload = "auto";
      var src = p.ac.createMediaElementSource(v), dest = p.ac.createMediaStreamDestination();
      src.connect(dest);
      var stream = new MediaStream(canvas.captureStream(fps).getVideoTracks().concat(dest.stream.getAudioTracks()));
      var rec = new MediaRecorder(stream, { mimeType: p.mime, videoBitsPerSecond: p.vBps, audioBitsPerSecond: p.aBps });
      var cleanup = function () { clearInterval(timer); clearInterval(watchdog); v.ontimeupdate = v.onended = v.onerror = v.onloadeddata = null; try { v.pause(); v.removeAttribute("src"); v.load(); } catch (e) {} try { src.disconnect(); } catch (e) {} URL.revokeObjectURL(url); };
      var stop = function () { if (finished) return; finished = true; try { if (rec.state !== "inactive") rec.stop(); else { cleanup(); reject(codeErr("failed")); } } catch (e) { cleanup(); reject(codeErr("failed")); } };
      var draw = function () { try { g.drawImage(v, 0, 0, p.w, p.h); } catch (e) {} };
      rec.ondataavailable = function (e) { if (e.data && e.data.size) chunks.push(e.data); };
      rec.onerror = function () { cleanup(); reject(codeErr("failed")); };
      rec.onstop = function () { cleanup(); if (aborted) reject(codeErr("cancelled")); else resolve(new Blob(chunks, { type: p.mime.split(";")[0] })); };
      v.onerror = function () { finished = true; cleanup(); reject(codeErr("unplayable")); };
      v.ontimeupdate = function () { lastTick = Date.now(); if (p.onProgress) p.onProgress(Math.min(1, v.currentTime / p.dur)); };
      v.onended = function () { draw(); stop(); };
      if (p.signal) p.signal.addEventListener("abort", function () { aborted = true; stop(); });
      watchdog = setInterval(function () { if (Date.now() - lastTick > 25000) { aborted = false; stop(); } }, 5000);
      v.onloadeddata = function () {
        rec.start(1000);
        timer = setInterval(draw, Math.round(1000 / fps));
        var pr = v.play(); if (pr && pr.catch) pr.catch(function () { finished = true; cleanup(); reject(codeErr("blocked")); });
      };
      v.src = url;
    });
  }
  async function shrink(file, o) {
    o = o || {};
    if (!canShrink()) throw codeErr("unsupported");
    var AC = window.AudioContext || window.webkitAudioContext, ac = new AC();
    try { await ac.resume(); } catch (e) {}
    try {
      var meta = await readMeta(file);
      if (!meta || meta === "unknown") throw codeErr("unplayable");
      var maxBytes = o.maxBytes || cfg.maxBytes, target = maxBytes * 0.85, dur = meta.duration, aBps = 64000, minV = 160000;
      if (dur > cfg.maxShrinkSeconds) throw codeErr("toolong", { seconds: cfg.maxShrinkSeconds });
      var mime = recorderMime(), blob = null;
      for (var attempt = 0; attempt < 2; attempt++) {
        var factor = attempt === 0 ? 1 : 0.6;
        var vBps = Math.floor(target * 8 / dur) - aBps;
        if (vBps < minV) throw codeErr("toolong", { seconds: Math.max(1, Math.floor(target * 8 / (minV + aBps))) });
        vBps = Math.floor(Math.min(vBps, 2500000) * factor);
        var h = vBps >= 1500000 ? 720 : vBps >= 800000 ? 540 : vBps >= 400000 ? 360 : 240;
        h = Math.min(h, meta.height); var w = Math.round(meta.width * h / meta.height); w -= w % 2; h -= h % 2;
        blob = await record(file, { ac: ac, mime: mime, w: w, h: h, vBps: vBps, aBps: aBps, dur: dur, signal: o.signal, onProgress: function (f) { if (o.onProgress) o.onProgress(f); } });
        if (blob.size <= maxBytes) break;
      }
      if (!blob || blob.size > maxBytes) throw codeErr("toolong", { seconds: Math.max(1, Math.floor(dur * maxBytes / blob.size * 0.9)) });
      var base = String(file.name || "video").replace(/\.[^.]+$/, ""), mt = blob.type || "video/webm";
      return new File([blob], base + (/mp4/.test(mt) ? ".mp4" : ".webm"), { type: mt });
    } finally { try { ac.close(); } catch (e) {} }
  }

  function html(url, o) {
    o = o || {};
    if (!url || !cfg.allowUrl(url)) return "";
    var label = T("Play video");
    return '<div class="vplayer" data-vsrc="' + esc(url) + '"><button class="vplay" type="button" aria-label="' + esc(o.title ? label + ": " + o.title : label) + '"><span class="vicon" aria-hidden="true">\u25B6</span><span>' + esc(label) + "</span></button></div>";
  }
  function fail(box, url, why) {
    box.classList.remove("loading", "live"); box.classList.add("failed");
    var msg = why === 4 ? T("This video couldn't be played. The file may be missing, or in a format your browser doesn't support, such as a newer phone format.")
      : why === "slow" ? T("The video is taking too long to load.")
      : T("The video couldn't be loaded. Check your connection and try again.");
    box.innerHTML = '<div class="verr" role="alert"><p>' + esc(msg) + '</p><p><button class="vretry" type="button">' + esc(T("Try again")) +
      '</button> \u00B7 <a href="' + esc(url) + '" target="_blank" rel="noopener noreferrer">' + esc(T("Open the video file")) + "</a></p></div>";
    var b = box.querySelector(".vretry"); if (b) b.focus();
  }
  function start(box) {
    var url = box.getAttribute("data-vsrc");
    if (!url || !cfg.allowUrl(url)) return;
    box.classList.remove("failed", "live"); box.classList.add("loading");
    box.innerHTML = "";
    var v = document.createElement("video"), settled = false, slow;
    v.controls = true; v.playsInline = true; v.preload = "auto"; v.setAttribute("playsinline", "");
    box.appendChild(v);
    var ready = function () { if (settled) return; settled = true; clearTimeout(slow); box.classList.remove("loading"); box.classList.add("live"); };
    slow = setTimeout(function () { if (!settled) { settled = true; fail(box, url, "slow"); } }, cfg.slowMs);
    v.addEventListener("loadeddata", ready); v.addEventListener("playing", ready);
    v.addEventListener("error", function () { if (settled && !box.classList.contains("live")) return; settled = true; clearTimeout(slow); fail(box, url, v.error ? v.error.code : 0); });
    v.src = url;
    var pr = v.play(); if (pr && pr.catch) pr.catch(function () { ready(); });
  }
  document.addEventListener("click", function (e) {
    var t = e.target; if (!t || !t.closest) return;
    var play = t.closest(".vplay"); if (play) { e.preventDefault(); start(play.closest(".vplayer")); return; }
    var retry = t.closest(".vretry"); if (retry) { e.preventDefault(); start(retry.closest(".vplayer")); return; }
    var sh = t.closest(".vshrink"); if (sh && sh.parentNode && sh.parentNode._input) { e.preventDefault(); doShrink(sh.parentNode._input); return; }
    var cn = t.closest(".vcancel"); if (cn && cn.parentNode && cn.parentNode._input) { e.preventDefault(); var st = stateOf(cn.parentNode._input); if (st.abort) st.abort.abort(); }
  });
  document.addEventListener("play", function (e) {
    var cur = e.target; if (!cur || cur.tagName !== "VIDEO") return;
    var all = document.querySelectorAll("video");
    for (var i = 0; i < all.length; i++) if (all[i] !== cur && !all[i].paused) all[i].pause();
  }, true);
  document.addEventListener("close", function (e) {
    var d = e.target; if (!d || !d.querySelectorAll) return;
    var vs = d.querySelectorAll("video"); for (var i = 0; i < vs.length; i++) vs[i].pause();
  }, true);

  var states = new WeakMap();
  function stateOf(input) {
    var st = states.get(input);
    if (!st) { st = { token: 0, busy: false, note: null, abort: null }; states.set(input, st); }
    if (!st.note || !st.note.isConnected) {
      var n = document.createElement("div"); n.className = "vnote"; n.setAttribute("role", "status"); n.setAttribute("aria-live", "polite"); n._input = input;
      input.insertAdjacentElement("afterend", n); st.note = n;
    }
    return st;
  }
  function say(input, kind, text, extra) {
    var n = stateOf(input).note; n.className = "vnote" + (kind ? " " + kind : "");
    n.textContent = text || "";
    if (extra) n.appendChild(extra);
  }
  var button = function (cls, label) { var b = document.createElement("button"); b.type = "button"; b.className = cls; b.textContent = label; return b; };
  function isVideoInput(i) { return i && i.tagName === "INPUT" && i.type === "file" && /video\//i.test(i.getAttribute("accept") || ""); }
  function replaceFile(input, file) {
    var dt = new DataTransfer(); dt.items.add(file); input.files = dt.files;
    if (!input.files[0] || input.files[0].size !== file.size) throw codeErr("replace");
  }
  async function check(input) {
    var st = stateOf(input), token = ++st.token, f = input.files && input.files[0];
    if (st.abort) { try { st.abort.abort(); } catch (e) {} }
    if (!f) { st.busy = false; say(input, "", ""); return; }
    st.busy = true; say(input, "", T("Checking your video\u2026"));
    var info; try { info = await inspect(f); } catch (e) { info = { ok: true, unknown: true, name: f.name, size: f.size, type: typeOf(f) }; }
    if (token !== st.token) return;
    st.busy = false;
    if (info.problem === "type") { input.value = ""; return say(input, "err", T("That file type isn't supported. Please choose an MP4, WebM or MOV video.")); }
    if (info.problem === "unplayable") { input.value = ""; return say(input, "err", T("This video can't be played in most browsers. It may use a newer phone format. On an iPhone choose Settings, Camera, Formats, Most Compatible and record again, or choose an MP4 video.")); }
    if (info.tooBig) {
      var base = T("This video is {size} but the limit is {max}.", { size: fmtMB(info.size), max: fmtMB(cfg.maxBytes) });
      if (canShrink() && !info.unknown) { var b = button("vshrink", T("Make it smaller")); return say(input, "err", base + " ", b); }
      return say(input, "err", base + " " + T("Please choose a shorter or smaller video."));
    }
    var nf = normalize(f); if (nf !== f) { try { replaceFile(input, nf); } catch (e) {} }
    if (info.unknown) return say(input, "ok", T("{name}: {details}. Ready to upload.", { name: f.name, details: fmtMB(f.size) }) + " " + T("We couldn't preview this video, but you can still upload it."));
    say(input, "ok", T("{name}: {details}. Ready to upload.", { name: f.name, details: fmtTime(info.duration) + ", " + fmtMB(f.size) }));
  }
  async function doShrink(input) {
    var st = stateOf(input), f = input.files && input.files[0]; if (!f || st.busy) return;
    var token = ++st.token, ctl = new AbortController(); st.abort = ctl; st.busy = true;
    var n = st.note; n.className = "vnote"; n.textContent = T("Making your video smaller. Keep this tab open until it finishes.");
    var bar = document.createElement("progress"); bar.max = 100; bar.value = 0; n.appendChild(bar);
    n.appendChild(button("vcancel", T("Cancel")));
    try {
      var out = await shrink(f, { maxBytes: cfg.maxBytes, signal: ctl.signal, onProgress: function (p) { bar.value = Math.round(p * 100); } });
      if (token !== st.token) return;
      var info = await inspect(out);
      if (!info.ok || info.tooBig) throw codeErr("failed");
      replaceFile(input, out); st.busy = false;
      say(input, "ok", T("Done. Your video is now {size} and ready to upload.", { size: fmtMB(out.size) }));
    } catch (err) {
      if (token !== st.token) return;
      st.busy = false;
      var c = err && err.code;
      if (c === "cancelled") return say(input, "", T("Cancelled. You can choose a different video."));
      if (c === "replace") return say(input, "err", T("Your browser couldn't swap in the smaller video automatically. Please choose a smaller video yourself."));
      if (c === "unsupported") return say(input, "err", T("Your browser can't make videos smaller. Please choose a shorter or smaller video."));
      if (c === "toolong") return say(input, "err", T("This video is too long to fit in {max}. The longest that can fit is about {seconds} seconds.", { max: fmtMB(cfg.maxBytes), seconds: (err.extra && err.extra.seconds) || "" }));
      say(input, "err", T("Couldn't make the video smaller. Please choose a shorter or smaller video."));
    } finally { if (st.abort === ctl) st.abort = null; }
  }
  document.addEventListener("change", function (e) { if (isVideoInput(e.target)) check(e.target); });

  var FORMATS = [["MP4 (H.264, works almost everywhere)", 'video/mp4; codecs="avc1.42E01E, mp4a.40.2"'], ["WebM (VP8)", 'video/webm; codecs="vp8, vorbis"'],
                 ["WebM (VP9)", 'video/webm; codecs="vp9, opus"'], ["MOV (QuickTime)", "video/quicktime"], ["MP4 (HEVC, newer iPhones)", 'video/mp4; codecs="hvc1.1.6.L93.B0"']];
  function allowedByPolicy(url) {
    var m = document.querySelector('meta[http-equiv="Content-Security-Policy"]'); if (!m) return null;
    var d = /(?:^|;)\s*media-src\s+([^;]*)/i.exec(m.getAttribute("content") || ""); if (!d) return null;
    var u; try { u = new URL(url, location.href); } catch (e) { return false; }
    return d[1].trim().split(/\s+/).some(function (t) {
      if (t === "'self'") return u.origin === location.origin;
      if (t === "blob:" || t === "data:") return u.protocol === t;
      if (t.indexOf("*") >= 0) return new RegExp("^" + t.replace(/[.+?^${}()|[\]\\]/g, "\\$&").replace(/\*/g, "[^/]*") + "(/|$)").test(u.origin + "/");
      return u.origin === t;
    });
  }
  function headCheck(url, out) {
    if (typeof fetch !== "function") { out.advice.push("This browser cannot run the address check."); return Promise.resolve(); }
    return fetch(url, { method: "HEAD" }).then(function (r) {
      var ct = r.headers.get("content-type") || "(none)";
      out.server = { status: r.status, contentType: ct, size: r.headers.get("content-length") || "(unknown)", acceptsSeeking: /bytes/i.test(r.headers.get("accept-ranges") || "") };
      if (!r.ok) { out.problems.push(r.status === 404 ? "The server says this file does not exist (404). Check that the Supabase bucket is named post-videos, that it is Public, and that the file is still there." : "The server refused the request (" + r.status + "). If the bucket is private, make it Public in Supabase, Storage."); return; }
      if (!/^video\//i.test(ct)) out.problems.push("The server labels this file \"" + ct + "\" instead of a video type, so browsers may refuse it. Upload the video again (new uploads are labelled correctly).");
      if (/quicktime/i.test(ct)) out.advice.push("MOV files often do not play in Chrome or Firefox. MP4 or WebM is safer.");
      if (!out.server.acceptsSeeking) out.advice.push("The server does not offer partial downloads, so jumping ahead in the video may be slow.");
    }, function () { out.problems.push("Couldn't reach this address. The page's security policy, an ad blocker, a different network or the server's cross-site settings may be blocking it."); });
  }
  function openCheck(url, out) {
    return new Promise(function (resolve) {
      var v = document.createElement("video"), tm, fin = function (ok, why) {
        clearTimeout(tm); v.onloadedmetadata = v.onerror = null;
        try { v.removeAttribute("src"); v.load(); } catch (e) {}
        out.thisBrowserCanOpenIt = ok;
        if (!ok) out.problems.push(why); resolve();
      };
      v.preload = "metadata"; v.muted = true;
      tm = setTimeout(function () { fin(false, "The browser did not start loading it within " + Math.round(Math.min(10000, cfg.slowMs / 2) / 1000) + " seconds. A slow connection or a very slow server."); }, Math.min(10000, cfg.slowMs / 2));
      v.onloadedmetadata = function () { v.videoWidth > 0 ? (out.length = fmtTime(v.duration), fin(true)) : fin(false, "The file opens but has no picture this browser can show (for example a newer phone format)."); };
      v.onerror = function () { fin(false, "This browser could not open the file (media error " + (v.error ? v.error.code : "?") + "). It may be missing, damaged, or in a format this browser cannot play."); };
      v.src = url;
    });
  }
  function diagnose(url) {
    var out = { videosJs: "loaded", formatsThisBrowserPlays: {}, canMakeVideosSmaller: canShrink(), problems: [], advice: [] }, probe = document.createElement("video");
    FORMATS.forEach(function (f) { out.formatsThisBrowserPlays[f[0]] = probe.canPlayType(f[1]) || "no"; });
    var done = function () {
      out.verdict = out.problems.length ? out.problems.length + " problem(s) found. See \"problems\"." : (url ? "No problems found. If a visitor still cannot play it, ask which phone and browser they use." : "Add the video's address to check it: IsleVideos.diagnose(\"...\")");
      try { console.log("Isle Connect video check\n" + JSON.stringify(out, null, 2)); } catch (e) {}
      return out;
    };
    if (!url) return Promise.resolve(done());
    out.address = url;
    if (!cfg.allowUrl(url)) { out.problems.push("index.html does not approve this address. Only videos stored in your own Supabase project are shown. Check SUPABASE_URL in the CONFIG block."); return Promise.resolve(done()); }
    if (allowedByPolicy(url) === false) out.problems.push("The page's security policy (media-src) blocks this address. If you use a custom Supabase domain, add it to media-src, connect-src and img-src in index.html and in your _headers or .htaccess file.");
    return headCheck(url, out).then(function () { return openCheck(url, out); }).then(done);
  }

  window.IsleVideos = {
    version: 1,
    diagnose: diagnose,
    configure: function (o) { for (var k in o) if (Object.prototype.hasOwnProperty.call(cfg, k) && o[k] != null) cfg[k] = o[k]; },
    html: html,
    typeOf: typeOf,
    normalize: normalize,
    inspect: inspect,
    canShrink: canShrink,
    shrink: shrink,
    busy: function (input) { var st = input && states.get(input); return !!(st && st.busy); }
  };
})();

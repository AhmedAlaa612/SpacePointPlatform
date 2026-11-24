/* SpacePoint LMS Book Bridge
 * Runs in <head> before inline book scripts (early phase) and attaches DOM hooks
 * on DOMContentLoaded. Handles:
 *  - Shared-device localStorage isolation & Postgres state hydration
 *  - Server-enforced Teacher mode lock
 *  - Clean branding swap (SPACE. -> SpacePoint logo) & AI chip removal
 *  - Mobile spread stacking (keeps reading + practice together in 1 vertical scroll)
 *  - PostMessage bidirectional sync (progress, stars, quizzes, your-turn, notebook, labs)
 */
(function () {
  "use strict";

  var html = document.documentElement;
  if (window.parent !== window) {
    html.dataset.spEmbedded = "1";
  }

  function parseConfig() {
    try {
      var meta = document.querySelector('meta[name="sp-book-config"]');
      if (!meta) return {};
      var raw = meta.getAttribute("content") || "{}";
      return JSON.parse(raw);
    } catch (_err) {
      return {};
    }
  }

  var CFG_META = parseConfig();
  var BOOK_ID = CFG_META.bookId || "default";
  var USER_ID = CFG_META.userId || "anon";
  var CAN_TEACHER = Boolean(CFG_META.canTeacher);
  var RUNTIME_BASE = (CFG_META.runtimeBase || "__sp_runtime__").replace(/\/$/, "");
  var INITIAL_STATE = CFG_META.initialState && typeof CFG_META.initialState === "object" ? CFG_META.initialState : {};
  var INITIAL_VISITED = Array.isArray(CFG_META.visitedSpreads) ? CFG_META.visitedSpreads : [];
  var START_SPREAD = CFG_META.startSpread || "";
  var START_CHAPTER = CFG_META.startChapter || "";
  var START_PROFILE = CFG_META.startProfile || "";
  var START_THEME = CFG_META.startTheme || "";
  var START_LANG = CFG_META.startLang || "";

  var OWNER_KEY = USER_ID + ":" + BOOK_ID;
  var LS_PREFIX = "satkit-book:";

  // 1. Isolate shared devices and hydrate Postgres state BEFORE book JS reads localStorage
  try {
    var prevOwner = localStorage.getItem("sp-book-owner");
    if (prevOwner !== OWNER_KEY) {
      var toRemove = [];
      for (var i = 0; i < localStorage.length; i++) {
        var k = localStorage.key(i);
        if (k && k.indexOf(LS_PREFIX) === 0) toRemove.push(k);
      }
      toRemove.forEach(function (k) { localStorage.removeItem(k); });
      localStorage.setItem("sp-book-owner", OWNER_KEY);
    }

    // Apply initial state from Postgres if present
    Object.keys(INITIAL_STATE).forEach(function (k) {
      if (k === "teacher" && !CAN_TEACHER) return;
      var val = INITIAL_STATE[k];
      if (val !== undefined) {
        localStorage.setItem(LS_PREFIX + k, typeof val === "string" ? val : JSON.stringify(val));
      }
    });

    if (!CAN_TEACHER) {
      localStorage.setItem(LS_PREFIX + "teacher", JSON.stringify("0"));
    }
    if (localStorage.getItem(LS_PREFIX + "asked") === null) {
      localStorage.setItem(LS_PREFIX + "asked", JSON.stringify(1));
    }
    if (START_THEME) {
      localStorage.setItem(LS_PREFIX + "theme", JSON.stringify(START_THEME));
      html.dataset.theme = START_THEME;
    }
    if (START_LANG === "en" || START_LANG === "ar") {
      localStorage.setItem(LS_PREFIX + "lang", JSON.stringify(START_LANG));
    }
    if (START_SPREAD) {
      localStorage.setItem(LS_PREFIX + "spread", JSON.stringify(START_SPREAD));
    }
  } catch (_e) {}

  // 2. Keep reading + interactive practice paired on mobile & skip jarring 3D page clones
  var origMatchMedia = window.matchMedia ? window.matchMedia.bind(window) : null;
  if (origMatchMedia) {
    window.matchMedia = function (query) {
      if (typeof query === "string") {
        if (query.indexOf("max-width:820px") !== -1 || query.indexOf("max-width: 820px") !== -1) {
          return {
            matches: false,
            media: query,
            onchange: null,
            addListener: function () {},
            removeListener: function () {},
            addEventListener: function () {},
            removeEventListener: function () {},
            dispatchEvent: function () { return false; },
          };
        }
        if (query.indexOf("prefers-reduced-motion") !== -1) {
          if (window.innerWidth <= 900) {
            return {
              matches: true,
              media: query,
              onchange: null,
              addListener: function () {},
              removeListener: function () {},
              addEventListener: function () {},
              removeEventListener: function () {},
              dispatchEvent: function () { return false; },
            };
          }
          return origMatchMedia(query);
        }
      }
      return origMatchMedia(query);
    };
  }

  // 3. State tracking & Storage.prototype.setItem interception
  var visitedSet = new Set(INITIAL_VISITED.filter(Boolean));
  var lastStars = {};
  try {
    var sRaw = localStorage.getItem(LS_PREFIX + "stars");
    if (sRaw) lastStars = JSON.parse(sRaw) || {};
  } catch (_e) {}

  function postToParent(type, payload) {
    try {
      if (window.parent && window.parent !== window) {
        window.parent.postMessage({ type: type, bookId: BOOK_ID, payload: payload }, "*");
      }
    } catch (_e) {}
  }

  var syncTimer = null;
  function collectRawState() {
    var raw = {};
    try {
      for (var i = 0; i < localStorage.length; i++) {
        var key = localStorage.key(i);
        if (!key || key.indexOf(LS_PREFIX) !== 0) continue;
        var shortKey = key.slice(LS_PREFIX.length);
        if (shortKey === "asked" || shortKey === "pendingPlan") continue;
        try {
          raw[shortKey] = JSON.parse(localStorage.getItem(key));
        } catch (_e) {
          raw[shortKey] = localStorage.getItem(key);
        }
      }
    } catch (_e) {}
    return raw;
  }

  function getActiveSpreads() {
    var all = Array.prototype.slice.call(document.querySelectorAll(".spread[data-name]"));
    return all.filter(function (el) {
      var n = el.getAttribute("data-name");
      return n && n !== "key" && n.indexOf("${") === -1;
    });
  }

  function getCurrentSpreadEl() {
    var shownPage = document.querySelector(".page.show");
    if (shownPage) {
      var sp = shownPage.closest(".spread");
      if (sp) return sp;
    }
    var h = (window.location.hash || "").replace(/^#/, "");
    if (h) {
      var byHash = document.querySelector('.spread[data-name="' + CSS.escape(h) + '"]');
      if (byHash) return byHash;
    }
    return null;
  }

  function getBookStatusSnapshot() {
    var sp = getCurrentSpreadEl();
    var spreadName = sp ? sp.getAttribute("data-name") : "";
    var chapterKey = sp ? (sp.getAttribute("data-ch") || "") : "";
    if (chapterKey && /^[0-9]+$/.test(chapterKey)) {
      chapterKey = "m" + chapterKey;
    }
    if (spreadName && spreadName !== "cover" && spreadName !== "key") {
      visitedSet.add(spreadName);
    }

    var raw = collectRawState();
    var stars = (raw.stars && typeof raw.stars === "object") ? raw.stars : {};
    var starsEarned = Object.keys(stars).reduce(function (acc, k) { return acc + (Number(stars[k]) || 0); }, 0);
    var gameCount = Math.max(Object.keys(stars).length, document.querySelectorAll("[data-stars]").length);
    var starsPossible = gameCount * 3;

    var allOrdered = getActiveSpreads();
    var totalSpreadsCount = allOrdered.length;
    var spreadIdx = 0;
    var pnEl = document.getElementById("pn");
    if (pnEl && pnEl.textContent) {
      var pnMatch = pnEl.textContent.match(/(\d+)\s*\/\s*(\d+)/);
      if (pnMatch) {
        spreadIdx = Number(pnMatch[1]) || 0;
        totalSpreadsCount = Number(pnMatch[2]) || totalSpreadsCount;
      }
    }

    var totalSpreads = Math.max(1, totalSpreadsCount - 1);
    var pct = Math.min(100, Math.round((visitedSet.size / totalSpreads) * 100));

    var lang = html.dataset.lang || "en";
    var titleEn = sp ? (sp.getAttribute("data-ten") || "") : "";
    var titleAr = sp ? (sp.getAttribute("data-tar") || "") : "";
    if (!titleEn && sp) {
      var h2 = sp.querySelector(".page.side-a h2, .page h2, .page h1");
      if (h2) {
        var enSpan = h2.querySelector(".en");
        var arSpan = h2.querySelector(".ar");
        titleEn = enSpan ? enSpan.textContent.trim() : h2.textContent.trim();
        titleAr = arSpan ? arSpan.textContent.trim() : titleEn;
      }
    }
    var activeProfile = (raw.cfg && raw.cfg.p) ? raw.cfg.p : "all";

    return {
      currentSpread: spreadName || "cover",
      currentChapter: chapterKey || "",
      currentTitle: lang === "ar" ? (titleAr || titleEn) : (titleEn || titleAr),
      activeProfile: activeProfile,
      lang: lang,
      theme: html.dataset.theme || "light",
      teacher: html.dataset.teacher === "1" && CAN_TEACHER,
      visitedSpreads: Array.from(visitedSet),
      stars: stars,
      starsEarned: starsEarned,
      starsPossible: starsPossible,
      completionPct: pct,
      spreadIndex: spreadIdx,
      totalSpreads: totalSpreadsCount,
      rawState: raw,
    };
  }

  function scheduleSync(immediate) {
    if (syncTimer) clearTimeout(syncTimer);
    if (immediate) {
      postToParent("SP_BOOK_STATE_SYNC", getBookStatusSnapshot());
      return;
    }
    syncTimer = setTimeout(function () {
      postToParent("SP_BOOK_STATE_SYNC", getBookStatusSnapshot());
    }, 1200);
  }

  function emitExercise(payload) {
    var snap = getBookStatusSnapshot();
    postToParent("SP_BOOK_EXERCISE_RESPONSE", {
      chapter_key: payload.chapter_key || snap.currentChapter || null,
      exercise_key: String(payload.exercise_key || "").slice(0, 160),
      exercise_type: payload.exercise_type || "quiz",
      prompt_text: payload.prompt_text ? String(payload.prompt_text).slice(0, 1000) : null,
      answer_json: payload.answer_json || {},
      is_correct: typeof payload.is_correct === "boolean" ? payload.is_correct : null,
      score_stars: typeof payload.score_stars === "number" ? payload.score_stars : null,
      max_stars: typeof payload.max_stars === "number" ? payload.max_stars : null,
    });
  }

  // Expose official SpacePoint Book API for future books
  window.SpacePointBook = {
    getContext: function () {
      return {
        bookId: BOOK_ID,
        userId: USER_ID,
        canTeacher: CAN_TEACHER,
        lang: html.dataset.lang || "en",
        theme: html.dataset.theme || "light",
      };
    },
    reportExercise: function (data) {
      if (!data || !data.exercise_key) return;
      emitExercise(data);
      scheduleSync(false);
    },
    setProgress: function (data) {
      if (data && Array.isArray(data.visitedSpreads)) {
        data.visitedSpreads.forEach(function (s) { visitedSet.add(s); });
      }
      scheduleSync(Boolean(data && data.immediate));
    },
  };

  // Intercept localStorage writes
  var origSetItem = Storage.prototype.setItem;
  Storage.prototype.setItem = function (key, value) {
    if (this === window.localStorage && typeof key === "string" && key.indexOf(LS_PREFIX) === 0) {
      var shortKey = key.slice(LS_PREFIX.length);
      if (shortKey === "teacher" && !CAN_TEACHER) {
        value = JSON.stringify("0");
      }
      origSetItem.call(this, key, value);

      if (shortKey === "stars") {
        try {
          var nextStars = JSON.parse(value) || {};
          Object.keys(nextStars).forEach(function (gKey) {
            if (nextStars[gKey] !== lastStars[gKey]) {
              var gameEl = document.querySelector('[data-stars="' + CSS.escape(gKey) + '"]');
              var sp = gameEl ? gameEl.closest(".spread") : null;
              var ch = sp ? (sp.getAttribute("data-ch") || "") : "";
              if (/^[0-9]+$/.test(ch)) ch = "m" + ch;
              var titleEl = gameEl ? gameEl.closest(".game, .page").querySelector("h2") : null;
              var prompt = titleEl ? titleEl.textContent.trim() : gKey;
              emitExercise({
                chapter_key: ch || null,
                exercise_key: "game:" + gKey,
                exercise_type: "game",
                prompt_text: prompt,
                answer_json: { game_key: gKey, stars: nextStars[gKey] },
                is_correct: Number(nextStars[gKey]) >= 1,
                score_stars: Number(nextStars[gKey]) || 0,
                max_stars: 3,
              });
            }
          });
          lastStars = nextStars;
        } catch (_e) {}
      } else if (/^u\d+lab$/.test(shortKey)) {
        try {
          var labVal = JSON.parse(value);
          emitExercise({
            chapter_key: shortKey.replace("lab", ""),
            exercise_key: "lab:" + shortKey,
            exercise_type: "lab",
            prompt_text: "Lab Data Table (" + shortKey.replace("lab", "").toUpperCase() + ")",
            answer_json: { rows: labVal },
            is_correct: true,
          });
        } catch (_e) {}
      } else if (shortKey === "spread") {
        postToParent("SP_BOOK_NAVIGATED", getBookStatusSnapshot());
      }
      scheduleSync(false);
      return;
    }
    return origSetItem.apply(this, arguments);
  };

  function cleanupBrandingAndChips() {
    // Replace SPACE. text logo with real SpacePoint white logo
    document.querySelectorAll(".brand").forEach(function (el) {
      if ((el.textContent || "").trim().indexOf("SPACE") !== -1) {
        var img = document.createElement("img");
        img.src = RUNTIME_BASE + "/logo-white.png";
        img.alt = "SpacePoint";
        img.className = "sp-brand-logo";
        el.replaceWith(img);
      }
    });

    // Remove AI-looking Bloom/5C/Hat chips
    document.querySelectorAll(".btab, .bbadge, .cchip, .hatrow, .tags").forEach(function (el) {
      el.remove();
    });

    if (!CAN_TEACHER) {
      document.querySelectorAll(".tn, .tcard").forEach(function (el) { el.remove(); });
      html.dataset.teacher = "0";
    }
  }

  function gotoSpreadByName(name) {
    if (!name || name === "key") return false;
    if (typeof window.viewOfSpread === "function" && typeof window.go === "function") {
      var targetIdx = window.viewOfSpread(name);
      window.go(targetIdx);
      if (window.innerWidth <= 900) window.scrollTo({ top: 0, behavior: "instant" });
      return true;
    }
    var btn = document.querySelector('[data-goto="' + CSS.escape(name) + '"]');
    if (btn) {
      btn.click();
      return true;
    }
    return false;
  }

  function gotoChapterByKey(chKey) {
    if (!chKey) return false;
    var norm = chKey.replace(/^m([0-9]+)$/, "$1");
    var el = document.querySelector('.spread[data-ch="' + CSS.escape(norm) + '"]') ||
      document.querySelector('.spread[data-ch="' + CSS.escape(chKey) + '"]');
    if (el) {
      var name = el.getAttribute("data-name");
      if (name) return gotoSpreadByName(name);
    }
    return false;
  }

  document.addEventListener("DOMContentLoaded", function () {
    cleanupBrandingAndChips();

    // Wrap window.go to automatically skip the removed Colour Key ('key') spread & scroll top on mobile
    if (typeof window.go === "function") {
      var origGo = window.go;
      window.go = function (to) {
        var curElBefore = getCurrentSpreadEl();
        var prevName = (curElBefore && curElBefore.getAttribute("data-name")) || "";
        var keyIdx = typeof window.viewOfSpread === "function" ? window.viewOfSpread("key") : -1;
        if (keyIdx >= 0 && to === keyIdx) {
          var prevIdx = typeof window.viewOfSpread === "function" && prevName ? window.viewOfSpread(prevName) : -1;
          to = to + (prevIdx >= 0 && to < prevIdx ? -1 : 1);
        }
        origGo.call(this, to);
        var curEl = getCurrentSpreadEl();
        if (curEl && curEl.getAttribute("data-name") === "key") {
          var forward = prevName === "welcome" || prevName === "cover";
          origGo.call(this, to + (forward ? 1 : -1));
        }
        if (window.innerWidth <= 900) {
          window.scrollTo({ top: 0, behavior: "instant" });
        }
        postToParent("SP_BOOK_NAVIGATED", getBookStatusSnapshot());
        setTimeout(function () {
          postToParent("SP_BOOK_NAVIGATED", getBookStatusSnapshot());
          scheduleSync(false);
        }, 820);
      };
    }

    // If initial landing landed on 'key', advance past it
    var curInit = getCurrentSpreadEl();
    if (curInit && curInit.getAttribute("data-name") === "key" && typeof window.go === "function") {
      window.go(3);
    }

    // Apply requested initial profile if provided
    if (START_PROFILE && typeof window.presetCfg === "function" && typeof window.applyCfg === "function") {
      try {
        window.applyCfg(window.presetCfg(START_PROFILE));
        cleanupBrandingAndChips();
      } catch (_e) {}
    }

    // Navigate to requested chapter or spread if specified
    if (START_SPREAD) {
      gotoSpreadByName(START_SPREAD);
    } else if (START_CHAPTER) {
      gotoChapterByKey(START_CHAPTER);
    }

    // Capture Notebook textareas ([data-nb])
    var nbTimers = {};
    function syncNotebook(ta) {
      if (!ta || !ta.id) return;
      var sp = ta.closest(".spread");
      var ch = sp ? (sp.getAttribute("data-ch") || "") : "";
      if (/^[0-9]+$/.test(ch)) ch = "m" + ch;
      var lab = document.querySelector('label[for="' + CSS.escape(ta.id) + '"]');
      var enLab = lab ? lab.querySelector(".en") : null;
      var prompt = enLab ? enLab.textContent.trim() : (lab ? lab.textContent.trim() : ta.id);
      emitExercise({
        chapter_key: ch || null,
        exercise_key: "nb:" + ta.id,
        exercise_type: "notebook",
        prompt_text: prompt,
        answer_json: { id: ta.id, text: ta.value || "" },
        is_correct: Boolean((ta.value || "").trim().length > 0),
      });
    }
    document.addEventListener("input", function (e) {
      var ta = e.target && e.target.closest ? e.target.closest("[data-nb]") : null;
      if (!ta) return;
      if (nbTimers[ta.id]) clearTimeout(nbTimers[ta.id]);
      nbTimers[ta.id] = setTimeout(function () { syncNotebook(ta); }, 900);
    });
    document.addEventListener("change", function (e) {
      var ta = e.target && e.target.closest ? e.target.closest("[data-nb]") : null;
      if (ta) syncNotebook(ta);
    });

    // Capture "Your Turn" checks ([data-ytgo]) in capture phase
    document.addEventListener("click", function (e) {
      var btn = e.target && e.target.closest ? e.target.closest("[data-ytgo]") : null;
      if (!btn) return;
      var box = btn.closest("[data-yt]");
      if (!box) return;
      var ytId = box.getAttribute("data-yt") || "yt";
      var inp = box.querySelector("input");
      var entered = inp ? inp.value : "";
      var sp = box.closest(".spread");
      var ch = sp ? (sp.getAttribute("data-ch") || "") : "";
      if (/^[0-9]+$/.test(ch)) ch = "m" + ch;
      var qEl = box.querySelector("p, .en, span");
      var prompt = qEl ? qEl.textContent.trim() : ytId;
      setTimeout(function () {
        var msg = box.querySelector("[data-ytmsg]");
        var ok = msg ? msg.classList.contains("ok") : null;
        emitExercise({
          chapter_key: ch || null,
          exercise_key: "yt:" + ytId,
          exercise_type: "your_turn",
          prompt_text: prompt,
          answer_json: {
            value: entered,
            expected: box.getAttribute("data-a"),
            tolerance: box.getAttribute("data-tol"),
          },
          is_correct: ok,
        });
      }, 40);
    }, true);

    // Capture chapter quiz & mixed problem checks ([data-q], [data-qq], [data-pq]) in capture phase
    document.addEventListener("click", function (e) {
      var btn = e.target && e.target.closest ? e.target.closest("[data-q], [data-qq], [data-pq]") : null;
      if (!btn) return;
      var card = btn.closest("div[style*='border:1px solid'], .stp") || (btn.parentElement && btn.parentElement.parentElement);
      var sp = btn.closest(".spread");
      var ch = sp ? (sp.getAttribute("data-ch") || "") : "";
      if (/^[0-9]+$/.test(ch)) ch = "m" + ch;
      var attr = btn.hasAttribute("data-q") ? "data-q" : btn.hasAttribute("data-qq") ? "data-qq" : "data-pq";
      var idx = btn.getAttribute(attr) || "0";
      var kind = attr === "data-pq" ? "prob" : "quiz";
      var qBox = btn.closest("[id]");
      var qPrefix = qBox ? qBox.id : (ch || "ch3");

      // Read answer BEFORE index.html re-renders
      var val = "";
      if (card) {
        var numInp = card.querySelector("input[type='number'], textarea");
        var rad = card.querySelector("input[type='radio']:checked");
        if (rad) {
          var radLab = rad.closest("label");
          val = radLab ? radLab.textContent.trim() : rad.value;
        } else if (numInp) {
          val = numInp.value;
        }
      }
      var promptNode = card ? card.querySelector("div:first-child") : null;
      var promptText = promptNode ? promptNode.textContent.trim() : ("Q" + (Number(idx) + 1));

      setTimeout(function () {
        var ok = null;
        var container = qBox || (sp || document);
        var renderedBtn = container.querySelector("[" + attr + '="' + CSS.escape(idx) + '"]');
        var renderedCard = renderedBtn ? (renderedBtn.closest("div[style*='border:1px solid'], .stp") || (renderedBtn.parentElement && renderedBtn.parentElement.parentElement)) : card;
        if (renderedCard) {
          var msgEl = renderedCard.querySelector(".msg");
          if (msgEl) {
            if (msgEl.classList.contains("ok")) ok = true;
            else if (msgEl.classList.contains("no")) ok = false;
          }
        }
        emitExercise({
          chapter_key: ch || null,
          exercise_key: kind + ":" + qPrefix + ":" + idx,
          exercise_type: "quiz",
          prompt_text: promptText,
          answer_json: { answer: val, index: Number(idx) },
          is_correct: ok,
        });
      }, 45);
    }, true);

    // Trigger canvas resize once CSS finishes laying out the 2-column / mobile grid
    setTimeout(function () {
      window.dispatchEvent(new Event("resize"));
      postToParent("SP_BOOK_READY", getBookStatusSnapshot());
      scheduleSync(true);
    }, 120);
  });

  // Listen to commands from the parent SpacePoint React Reader
  window.addEventListener("message", function (e) {
    if (!e.data || typeof e.data !== "object") return;
    var msg = e.data;
    if (msg.type !== "SP_BOOK_CMD") return;
    var cmd = msg.cmd;
    var val = msg.value;

    if (cmd === "setTheme" && (val === "light" || val === "dark")) {
      var themeBtn = document.querySelector('.seg[data-set="theme"] button[data-v="' + val + '"]');
      if (themeBtn && html.dataset.theme !== val) themeBtn.click();
      html.dataset.theme = val;
      try { localStorage.setItem(LS_PREFIX + "theme", JSON.stringify(val)); } catch (_e) {}
    } else if (cmd === "setLang" && (val === "en" || val === "ar")) {
      var langBtn = document.querySelector('.seg[data-set="lang"] button[data-v="' + val + '"]');
      if (langBtn) langBtn.click();
    } else if (cmd === "setTeacher") {
      var want = CAN_TEACHER && Boolean(val) ? "1" : "0";
      var tBtn = document.querySelector('.seg[data-set="teacher"] button[data-v="' + want + '"]');
      if (tBtn) tBtn.click();
      html.dataset.teacher = want;
    } else if (cmd === "setProfile" && typeof val === "string") {
      if (typeof window.presetCfg === "function" && typeof window.applyCfg === "function") {
        window.applyCfg(window.presetCfg(val));
        cleanupBrandingAndChips();
        postToParent("SP_BOOK_NAVIGATED", getBookStatusSnapshot());
        scheduleSync(false);
      }
    } else if (cmd === "gotoSpread" && typeof val === "string") {
      gotoSpreadByName(val);
    } else if (cmd === "gotoChapter" && typeof val === "string") {
      gotoChapterByKey(val);
    } else if (cmd === "openToc") {
      var tocBtn = document.getElementById("go-toc");
      if (tocBtn) tocBtn.click();
    } else if (cmd === "openFx") {
      var fxBtn = document.getElementById("go-fx");
      if (fxBtn) fxBtn.click();
    } else if (cmd === "openMissionFile") {
      if (typeof window.openDlg === "function" && typeof window.mfView === "function") {
        window.openDlg(window.mfView);
      }
    } else if (cmd === "prev") {
      var prevBtn = document.getElementById("prev");
      if (prevBtn) prevBtn.click();
    } else if (cmd === "next") {
      var nextBtn = document.getElementById("next");
      if (nextBtn) nextBtn.click();
    }
  });

  // Best-effort flush before closing/hiding
  function flushSync() {
    postToParent("SP_BOOK_STATE_SYNC", getBookStatusSnapshot());
  }
  window.addEventListener("pagehide", flushSync);
  document.addEventListener("visibilitychange", function () {
    if (document.visibilityState === "hidden") flushSync();
  });
})();

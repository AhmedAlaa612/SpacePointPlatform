/* <satkit-assembly> — pre-rendered PNG frame-sequence player.
   Plays the exact source renders (no 3D, no re-encoding, no detail loss).

   <script src="satkit-assembly.js" defer></script>
   <satkit-assembly base="/assets/satkit" fps="4" hold="2000" height="460"></satkit-assembly>

   `base` must contain manifest.json and the frames/ tree.
   Attributes: base, manifest (override the manifest URL), fps, hold (ms on final
   frame), height (css), accent, autoplay, loop ("false" = build once and stop
   on the final frame; call el.replay() to run it again), controls ("false" =
   no scrub rail, canvas fills the full host), zoom (scale multiplier on top
   of the normal fit-to-box size, e.g. "1.6" — crops in for a bigger, closer
   subject instead of leaving contain-fit padding around it).
*/
(() => {
  const CUT = [[10, 14], [1, 9], [48, 56], [60, 64], [38, 44], [65, 68]];

  class SatkitAssembly extends HTMLElement {
    connectedCallback() {
      if (this.__init) return;
      this.__init = true;
      const accent = this.getAttribute('accent') || '#9184d9';
      const height = this.getAttribute('height') || '460px';
      const controls = this.getAttribute('controls') !== 'false';
      const root = this.attachShadow({ mode: 'open' });
      const cssHeight = /^\d+$/.test(height) ? height + 'px' : height;
      root.innerHTML = `
        <style>
          /* With controls, the host auto-sizes to its content (fixed-height
             canvas + rail). Without, "height: 100%" on the canvas below has
             nothing to resolve against unless the host itself carries the
             size — so the host takes it directly instead. */
          :host { display: block; position: relative; ${controls ? '' : `height: ${cssHeight};`} }
          .wrap { display: flex; flex-direction: column; align-items: center; ${controls ? 'gap: 14px;' : ''} height: 100%; }
          canvas { display: block; width: 100%; height: ${controls ? cssHeight : '100%'}; cursor: pointer; }
          .rail { position: relative; width: 100%; height: 14px; display: flex; align-items: center; cursor: ew-resize; touch-action: none; }
          .track { position: absolute; left: 0; right: 0; height: 1px;
            background: linear-gradient(to right, transparent, rgba(255,255,255,.22) 12%, rgba(255,255,255,.22) 88%, transparent); }
          .fill { position: absolute; left: 0; width: 0%; height: 1px; background: ${accent}; }
          .head { position: absolute; left: 0; width: 2px; height: 9px; background: ${accent}; transform: translateX(-1px); }
          @media (prefers-reduced-motion: reduce) { .rail { display: none; } }
        </style>
        <div class="wrap">
          <canvas part="canvas"></canvas>
          ${controls ? '<div class="rail"><div class="track"></div><div class="fill"></div><div class="head"></div></div>' : ''}
        </div>`;
      this.canvas = root.querySelector('canvas');
      this.rail = root.querySelector('.rail');
      this.fill = root.querySelector('.fill');
      this.headEl = root.querySelector('.head');
      this.imgs = {};
      this.frames = [];
      this.i = 0;
      this.acc = 0;
      this.paused = false;
      this.base = (this.getAttribute('base') || '.').replace(/\/$/, '');

      this.canvas.addEventListener('click', () => { this.paused = !this.paused; });
      if (this.rail) {
        this.rail.addEventListener('pointerdown', (e) => {
          this.paused = true;
          const seek = (ev) => {
            const r = this.rail.getBoundingClientRect();
            const t = Math.max(0, Math.min(1, (ev.clientX - r.left) / r.width));
            this.i = Math.round(t * (this.frames.length - 1));
            this.acc = 0;
            this.draw();
          };
          seek(e);
          const up = () => {
            removeEventListener('pointermove', seek);
            removeEventListener('pointerup', up);
            this.paused = false;
          };
          addEventListener('pointermove', seek);
          addEventListener('pointerup', up);
        });
      }
      this.onResize = () => { this.fit(); this.draw(); };
      addEventListener('resize', this.onResize);

      // pause when offscreen
      if ('IntersectionObserver' in window) {
        this.io = new IntersectionObserver(([e]) => { this.offscreen = !e.isIntersecting; }, { threshold: 0.01 });
        this.io.observe(this);
      }

      const manifestUrl = this.getAttribute('manifest') || this.base + '/manifest.json';
      fetch(manifestUrl).then(r => r.json()).then(d => {
        this.data = d;
        const iso = d.seq.filter(f => f.view === 'iso');
        for (const [a, b] of CUT) for (let k = a; k <= b; k++) if (iso[k - 1]) this.frames.push(iso[k - 1]);
        this.fit();
        let n = 0;
        this.frames.forEach((f, idx) => {
          const img = new Image();
          img.decoding = 'async';
          img.onload = () => {
            this.imgs[f.src] = img;
            if (idx === 0) this.draw();
            if (++n >= Math.min(4, this.frames.length) && !this.raf) this.start();
          };
          img.onerror = () => { n++; };
          img.src = this.base + '/' + f.src;
        });
      });
    }

    disconnectedCallback() {
      cancelAnimationFrame(this.raf);
      this.raf = null;
      removeEventListener('resize', this.onResize);
      if (this.io) this.io.disconnect();
    }

    start() {
      if (this.getAttribute('autoplay') === 'false') { this.paused = true; }
      let last = performance.now();
      const fps = parseFloat(this.getAttribute('fps')) || 4;
      const hold = parseFloat(this.getAttribute('hold'));
      const holdMs = isNaN(hold) ? 2000 : hold;
      const tick = (ts) => {
        const dt = ts - last;
        last = ts;
        if (!this.paused && !this.offscreen) {
          this.acc += dt;
          const loops = this.getAttribute('loop') !== 'false';
          const step = 1000 / fps + (this.i === this.frames.length - 1 ? holdMs : 0);
          while (this.acc >= step) {
            this.acc -= step;
            if (!loops && this.i === this.frames.length - 1) {
              this.acc = 0;
              this.paused = true;
              this.dispatchEvent(new CustomEvent('assemblycomplete'));
              break;
            }
            this.i = (this.i + 1) % this.frames.length;
            this.draw();
          }
        }
        this.raf = requestAnimationFrame(tick);
      };
      this.raf = requestAnimationFrame(tick);
      this.draw();
    }

    replay() {
      this.i = 0;
      this.acc = 0;
      this.paused = false;
      this.draw();
    }

    fit() {
      const c = this.canvas, dpr = Math.min(devicePixelRatio || 1, 2);
      if (!c.clientWidth || !c.clientHeight) return;
      c.width = Math.round(c.clientWidth * dpr);
      c.height = Math.round(c.clientHeight * dpr);
    }

    draw() {
      const c = this.canvas;
      if (!c || !this.frames.length) return;
      const ctx = c.getContext('2d');
      ctx.clearRect(0, 0, c.width, c.height);
      const f = this.frames[this.i], img = f && this.imgs[f.src];
      if (img) {
        const u = this.data.groups[f.g].union;
        const zoom = parseFloat(this.getAttribute('zoom')) || 1;
        const padX = c.width * 0.02, padY = c.height * 0.03;
        const s = Math.min((c.width - padX * 2) / u[2], (c.height - padY * 2) / u[3]) * zoom;
        ctx.imageSmoothingEnabled = true;
        ctx.imageSmoothingQuality = 'high';
        // Centered on the union box in both axes — at zoom 1 this still
        // anchors to the bottom padding; above 1 it grows from the union's
        // own center, cropping past the canvas edges instead of overflowing
        // off just the top (a bottom-anchored crop would look like the
        // subject sank into the floor as it grows).
        const cx = c.width / 2, cy = c.height - padY - (u[3] / 2) * s;
        ctx.drawImage(img, cx - (u[0] + u[2] / 2) * s, cy - (u[1] + u[3] / 2) * s, img.width * s, img.height * s);
      }
      if (this.fill && this.headEl) {
        const p = this.frames.length > 1 ? (this.i / (this.frames.length - 1)) * 100 : 100;
        this.fill.style.width = p + '%';
        this.headEl.style.left = p + '%';
      }
    }
  }

  if (!customElements.get('satkit-assembly')) customElements.define('satkit-assembly', SatkitAssembly);
})();

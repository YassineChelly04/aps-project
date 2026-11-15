// Sijar · état partagé, accès API, formats, notifications, shader et cartes.

export const S = {
  exemples: [], methodes: {}, phases: {},
  inst: null, modele: 'gap', limite: 30, graine: 0, choisies: ['cs', 'bp', 'h1', 'h2', 'm1', 'm2'],
  jobs: {},            // cle -> {job_id, etat, phase, fraction, ecoule, resultat, erreur}
  comp: null,          // réponse /api/comparer
  choix: null,         // clé de la méthode retenue
  aff: null,           // affectation de travail {magasin: entrepot}
  base: null,          // affectation de la méthode retenue (avant modifications)
  ind: null,           // indicateurs de l'affectation de travail
  scenario: null,      // dernier scénario validé ou importé
  m2: { methodes: {}, service: 15, sc: null, choisies: ['ws', 'nsga', 'pls', 'eps'], limite: 20, graine: 0,
        job: null, res: null, sel: {}, cur: null, poids: 0.5 },
  plan: null, plans: [],
};

// ---------------------------------------------------------------- événements
const ecouteurs = new Set();
export const surChangement = (f) => ecouteurs.add(f);
export function changer() { ecouteurs.forEach((f) => f()); sauver(); }
function sauver() {
  try {
    localStorage.setItem('sijar.etat', JSON.stringify({
      inst: S.inst?.id || null, modele: S.modele, limite: S.limite, graine: S.graine,
      scenario: S.scenario, m2sc: S.m2.sc?.scenario || null,
    }));
  } catch (e) { /* stockage indisponible : sans conséquence */ }
}
export function relire() {
  try { return JSON.parse(localStorage.getItem('sijar.etat') || 'null'); } catch (e) { return null; }
}

// ---------------------------------------------------------------- API
export async function api(chemin, { json, form, methode } = {}) {
  const o = { method: methode || (json || form ? 'POST' : 'GET'), headers: {} };
  if (json) { o.headers['Content-Type'] = 'application/json'; o.body = JSON.stringify(json); }
  if (form) o.body = form;
  let r;
  try { r = await fetch(chemin, o); } catch (e) { throw new Error('Serveur injoignable. Vérifiez que uvicorn tourne.'); }
  let d = null;
  try { d = await r.json(); } catch (e) { /* corps vide */ }
  if (!r.ok) {
    const det = d?.detail;
    throw new Error(typeof det === 'string' ? det : det ? JSON.stringify(det) : `Erreur ${r.status}`);
  }
  return d;
}

// ---------------------------------------------------------------- formats
export const nf = (x, d = 0) => (x == null || !isFinite(x)) ? '—'
  : Number(x).toLocaleString('fr-FR', { minimumFractionDigits: d, maximumFractionDigits: d });
export const pct = (x, d = 0) => (x == null || !isFinite(x)) ? '—' : nf(100 * x, d) + ' %';
export const hm = (m) => { if (m == null || !isFinite(m)) return '—'; m = Math.round(m); return `${Math.floor(m / 60)} h ${String(m % 60).padStart(2, '0')}`; };
export const sec = (s) => s == null ? '—' : s < 0.1 ? nf(s, 3) + ' s' : s < 10 ? nf(s, 2) + ' s' : nf(s, 1) + ' s';
export const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
export const $ = (s, r = document) => r.querySelector(s);
export const $$ = (s, r = document) => [...r.querySelectorAll(s)];
export const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
export const couleur = (i) => css(`--e${(i % 10) + 1}`);
export const MODELES = { gap: 'Affectation (GAP)', sscflp: 'Localisation–affectation (SSCFLP)' };
export const etatCapacite = (u) => u > 1 + 1e-9 ? ['Dépassé', 's-dep', '--dep'] : u >= 0.85 ? ['Tendu', 's-tendu', '--tendu'] : ['Disponible', 's-ok', '--ok'];
export const reduit = matchMedia('(prefers-reduced-motion: reduce)');
export const NS = 'http://www.w3.org/2000/svg';
export function sv(tag, attrs, parent) {
  const e = document.createElementNS(NS, tag);
  for (const k in attrs) e.setAttribute(k, attrs[k]);
  if (parent) parent.appendChild(e);
  return e;
}
export function plural(n, mot, motPl) { return `${nf(n)} ${n > 1 ? (motPl || mot + 's') : mot}`; }

// ---------------------------------------------------------------- notifications
export function toast(msg, genre = 'info', duree = 4500) {
  const t = document.createElement('div');
  t.className = 'toast ' + genre;
  t.innerHTML = `<span>${esc(msg)}</span>`;
  const box = $('#toasts');
  box.appendChild(t);
  while (box.children.length > 3) box.firstElementChild.remove();
  setTimeout(() => t.remove(), duree);
}
export async function essayer(fn, msgErr) {
  try { return await fn(); } catch (e) { toast((msgErr ? msgErr + ' ' : '') + e.message, 'err', 8000); return undefined; }
}

// ---------------------------------------------------------------- shader (pavage étoilé de Kairouan)
const VS = `#version 300 es
in vec2 p;void main(){gl_Position=vec4(p,0.,1.);}`;
const FS = `#version 300 es
precision highp float;
uniform vec2 uR;uniform float uT;uniform vec3 uBg,uInk,uAcc,uSig;uniform vec2 uS[10];uniform int uN;uniform float uM,uK,uA;
out vec4 o;
float h21(vec2 p){p=fract(p*vec2(123.34,456.21));p+=dot(p,p+45.32);return fract(p.x*p.y);}
float vn(vec2 p){vec2 i=floor(p),f=fract(p);vec2 u=f*f*(3.-2.*f);return mix(mix(h21(i),h21(i+vec2(1,0)),u.x),mix(h21(i+vec2(0,1)),h21(i+vec2(1,1)),u.x),u.y);}
void main(){
  vec2 uv=gl_FragCoord.xy/uR.y;float px=1./uR.y;float asp=uR.x/uR.y;
  vec2 g=uv*uK;vec2 id=floor(g);vec2 f=fract(g)-.5;float cpx=px*uK;
  float sq=max(abs(f.x),abs(f.y))-.31;
  vec2 rf=vec2(f.x+f.y,f.x-f.y)*.70710678;float sr=max(abs(rf.x),abs(rf.y))-.31;
  float star=min(sq,sr);
  float edge=.5-max(abs(f.x),abs(f.y));
  float ln=1.-smoothstep(cpx*.4,cpx*1.3,abs(star));
  float grid=1.-smoothstep(cpx*.3,cpx*1.1,edge);
  float wave=vn(id*.23+vec2(uT*.06,uT*.035));
  float lit=smoothstep(.62,.66,wave)*(star<0.?1.:0.);
  vec3 c=uBg;
  if(uM>1.5){
    float prog=fract(uT*.22);float sweepX=prog*asp;
    float on=step(uv.x,sweepX)*(star<0.?1.:0.);
    c=mix(c,uAcc,on*.22);
    c=mix(c,uSig,1.-smoothstep(px*1.,px*2.5,abs(uv.x-sweepX)));
  } else { c=mix(c,uAcc,lit*uA*1.2); }
  c=mix(c,uInk,ln*uA);
  c=mix(c,uInk,grid*uA*.45);
  if(uM>.5&&uM<1.5&&uN>0){
    float d1=1e9,d2=1e9;
    for(int i=0;i<10;i++){if(i>=uN)break;vec2 s=vec2(uS[i].x*asp,uS[i].y);float dd=length(uv-s);if(dd<d1){d2=d1;d1=dd;}else if(dd<d2){d2=dd;}}
    if(uN>1){float b=1.-smoothstep(px*1.,px*2.4,d2-d1);float dash=step(.5,fract((uv.x-uv.y)*40.-uT*.3));c=mix(c,uInk,b*dash*.7);}
    for(int i=0;i<10;i++){if(i>=uN)break;vec2 q=uv-vec2(uS[i].x*asp,uS[i].y);
      float s2=max(abs(q.x),abs(q.y));c=mix(c,uInk,1.-smoothstep(px*6.,px*7.,s2));c=mix(c,uSig,1.-smoothstep(px*3.5,px*4.5,s2));
      float r=fract(uT*.14+float(i)*.29)*.2;float ring=1.-smoothstep(px*.8,px*2.,abs(max(abs(q.x),abs(q.y))-r));c=mix(c,uAcc,ring*(1.-r/.2)*.8);}
  }
  o=vec4(c,1.);
}`;
const rgb = (v) => { const h = css(v).replace('#', ''); return [0, 2, 4].map((i) => parseInt(h.substr(i, 2), 16) / 255); };
const champs = [];
export function champ(canvas, o) {
  let gl;
  try { gl = canvas.getContext('webgl2', { antialias: false }); } catch (e) { /* pas de WebGL2 */ }
  if (!gl) { canvas.hidden = true; return null; }
  const sh = (t, s) => { const x = gl.createShader(t); gl.shaderSource(x, s); gl.compileShader(x); if (!gl.getShaderParameter(x, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(x)); return x; };
  const pr = gl.createProgram();
  try { gl.attachShader(pr, sh(gl.VERTEX_SHADER, VS)); gl.attachShader(pr, sh(gl.FRAGMENT_SHADER, FS)); gl.linkProgram(pr); if (!gl.getProgramParameter(pr, gl.LINK_STATUS)) throw new Error('link'); }
  catch (e) { canvas.hidden = true; return null; }
  gl.useProgram(pr);
  const buf = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, buf);
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
  const loc = gl.getAttribLocation(pr, 'p'); gl.enableVertexAttribArray(loc); gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);
  const U = {}; ['uR', 'uT', 'uBg', 'uInk', 'uAcc', 'uSig', 'uS', 'uN', 'uM', 'uK', 'uA'].forEach((n) => U[n] = gl.getUniformLocation(pr, n));
  let col; const couleurs = () => { col = { bg: rgb('--sol'), ink: rgb('--encre'), acc: rgb('--bleu'), sig: rgb('--jaune') }; }; couleurs();
  let sites = o.sites || []; const t0 = performance.now(); let vis = false, raf = 0;
  const dessiner = () => {
    if (!canvas.clientWidth) return;
    const dpr = Math.min(devicePixelRatio || 1, o.dpr || 1.5);
    const w = Math.max(1, Math.round(canvas.clientWidth * dpr)), h = Math.max(1, Math.round(canvas.clientHeight * dpr));
    if (canvas.width !== w || canvas.height !== h) { canvas.width = w; canvas.height = h; }
    gl.viewport(0, 0, w, h);
    const t = reduit.matches ? 6 : (performance.now() - t0) / 1000;
    const s = new Float32Array(20);
    sites.slice(0, 10).forEach((p, i) => { s[i * 2] = p[0] + 0.01 * Math.sin(t * 0.13 + i * 1.7); s[i * 2 + 1] = p[1] + 0.01 * Math.cos(t * 0.11 + i); });
    gl.uniform2f(U.uR, w, h); gl.uniform1f(U.uT, t); gl.uniform3fv(U.uBg, col.bg); gl.uniform3fv(U.uInk, col.ink);
    gl.uniform3fv(U.uAcc, col.acc); gl.uniform3fv(U.uSig, col.sig); gl.uniform2fv(U.uS, s); gl.uniform1i(U.uN, Math.min(10, sites.length));
    gl.uniform1f(U.uM, o.mode); gl.uniform1f(U.uK, o.k); gl.uniform1f(U.uA, o.a); gl.drawArrays(gl.TRIANGLES, 0, 3);
  };
  const boucle = () => { raf = 0; dessiner(); if (vis && !reduit.matches && !document.hidden) raf = requestAnimationFrame(boucle); };
  const relancer = () => { if (!raf) raf = requestAnimationFrame(boucle); };
  new IntersectionObserver((es) => { vis = es[0].isIntersecting; if (vis) relancer(); }).observe(canvas);
  new ResizeObserver(() => { dessiner(); relancer(); }).observe(canvas);
  const c = { relancer, recolorer() { couleurs(); dessiner(); relancer(); }, sites(v) { sites = v; dessiner(); } };
  champs.push(c);
  return c;
}
document.addEventListener('visibilitychange', () => champs.forEach((c) => c.relancer()));
export function recolorerChamps() { champs.forEach((c) => c.recolorer()); }

// ---------------------------------------------------------------- bloc « calcul en cours »
export function blocCalcul(conteneur) {
  conteneur.innerHTML = `<div class="loader"><canvas aria-hidden="true"></canvas><div class="c"><div>
    <span class="lab">Calcul en cours</span><b data-r="titre">—</b><span class="mono" data-r="detail" style="font-size:12px"></span>
    <button class="btn sm danger" type="button" data-r="stop">Arrêter et garder la meilleure solution</button></div></div></div>`;
  const ch = champ(conteneur.querySelector('canvas'), { mode: 2, k: 10, a: 0.14 });
  return {
    maj({ titre, detail }) { conteneur.querySelector('[data-r=titre]').textContent = titre; conteneur.querySelector('[data-r=detail]').textContent = detail || ''; ch?.relancer(); },
    surStop(f) { conteneur.querySelector('[data-r=stop]').onclick = f; },
  };
}

// ---------------------------------------------------------------- cartes Leaflet (tuiles OpenStreetMap restylées)
export function carte(el) {
  const m = L.map(el, { zoomControl: true, attributionControl: true, scrollWheelZoom: true, preferCanvas: false });
  L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 18, attribution: '&copy; contributeurs <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
  }).addTo(m);
  m.setView([35.8, 10.2], 7);
  const couche = L.layerGroup().addTo(m);
  // Une carte créée ou cadrée dans un panneau masqué a une taille nulle : on mémorise le cadrage
  // demandé et on l'applique dès que le panneau devient visible.
  let attente = null, largeur = 0;
  const appliquer = () => { if (attente && el.clientWidth) { m.fitBounds(attente.b, { padding: [attente.pad, attente.pad], maxZoom: 12 }); attente = null; } };
  new ResizeObserver(() => {
    const avant = largeur; largeur = el.clientWidth;
    m.invalidateSize();
    if (!avant && largeur) appliquer();
  }).observe(el);
  return {
    m, couche,
    vider() { couche.clearLayers(); },
    cadrer(pts, pad = 30) {
      if (!pts.length) return;
      attente = { b: L.latLngBounds(pts), pad };
      if (el.clientWidth) { m.invalidateSize(); appliquer(); }
    },
  };
}
export function iconeEntrepot(id, coul, ouvert = true, taille = 26) {
  return L.divIcon({ className: '', iconSize: [taille + 8, taille], iconAnchor: [(taille + 8) / 2, taille / 2],
    html: `<div class="ent-ic ${ouvert ? '' : 'ferme'}" style="width:${taille + 8}px;height:${taille}px;background:${coul}">${esc(id)}</div>` });
}
export function iconeArret(n, coul) {
  return L.divIcon({ className: '', iconSize: [20, 20], iconAnchor: [10, 10],
    html: `<div class="stop-ic" style="width:20px;height:20px;border-color:${coul}">${n}</div>` });
}

// ---------------------------------------------------------------- graphique utilitaire
export function pas(etendue, n = 5) {
  const r = etendue / n, p = 10 ** Math.floor(Math.log10(r || 1)), m = r / p;
  return (m < 1.5 ? 1 : m < 3 ? 2 : m < 7 ? 5 : 10) * p;
}
// Étendue d'axe [a, b] élargie : jamais nulle ni plus fine que 1 % de la valeur (sinon, quand toutes
// les méthodes trouvent le même coût, le pas de graduation passe sous la précision des flottants).
export function etendre(a, b, marge = 0.08) {
  if (!isFinite(a) || !isFinite(b)) return [0, 1];
  const e = Math.max(b - a, Math.abs(b) * 0.01, 1e-6);
  const c = (a + b) / 2, lo = Math.min(a, c - e / 2), hi = Math.max(b, c + e / 2);
  return [lo - e * marge, hi + e * marge];
}
// Graduations « rondes » entre a et b (au plus 20, quelle que soit l'étendue).
export function graduations(a, b, n = 5) {
  const s = pas(b - a, n), out = [];
  for (let k = Math.ceil(a / s); out.length < 20; k++) { const v = k * s; if (v > b + 1e-9 * Math.abs(b)) break; out.push(v); }
  return { pas: s, valeurs: out };
}

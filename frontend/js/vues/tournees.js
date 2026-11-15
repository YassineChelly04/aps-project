// Station 04 · Tableau de bord 2 : fronts de Pareto distance / temps par entrepôt, choix du compromis, carte de la tournée.
import { S, $, $$, api, changer, nf, pct, hm, sec, esc, essayer, toast, carte, couleur, iconeEntrepot, iconeArret, css,
  etatCapacite, blocCalcul, sv, etendre, graduations, plural } from '../core.js';

let el, ctx, map, calc, minuteur = null, enVol = false;
export const STYLE = {
  ws: { c: '--bleu', f: 'rond' }, nsga: { c: '--ocre', f: 'triangle' }, pls: { c: '--e5', f: 'losange' }, eps: { c: '--encre', f: 'carre' },
};
export function forme(svg, f, x, y, c, r = 5) {
  if (f === 'rond') return sv('circle', { cx: x, cy: y, r: r - 0.8, style: `fill:var(${c})` }, svg);
  if (f === 'triangle') return sv('path', { d: `M${x} ${y - r - 0.5} L${x + r} ${y + r - 1} L${x - r} ${y + r - 1} Z`, style: `fill:var(${c})` }, svg);
  if (f === 'losange') return sv('path', { d: `M${x} ${y - r} L${x + r} ${y} L${x} ${y + r} L${x - r} ${y} Z`, style: `fill:var(${c})` }, svg);
  const g = sv('g', {}, svg);
  sv('rect', { x: x - r - 1, y: y - r - 1, width: 2 * r + 2, height: 2 * r + 2, style: `fill:none;stroke:var(${c});stroke-width:1.5` }, g);
  sv('rect', { x: x - 1.5, y: y - 1.5, width: 3, height: 3, style: `fill:var(${c})` }, g);
  return g;
}
export const iconeMethode = (k) => { const s = STYLE[k] || STYLE.eps; const svg = sv('svg', { viewBox: '0 0 16 16', width: 16, height: 16, 'aria-hidden': 'true' }); forme(svg, s.f, 8, 8, s.c, 5); return svg.outerHTML; };
const nomM = (k) => S.m2.methodes[k]?.nom || k;

export function init(racine, c) {
  el = racine; ctx = c;
  el.innerHTML = `
  <div class="vhead"><div class="t"><span class="lab">Station 04 · Tableau de bord 2</span><h2>Tourner depuis chaque entrepôt</h2>
    <p>Un véhicule part de l'entrepôt, visite chacun de ses magasins une fois et revient. Deux objectifs : la distance totale et le temps total (conduite + service). Chaque point du front est une tournée qu'on ne peut pas raccourcir sans l'allonger en temps.</p></div>
    <div class="row"><span class="chip" id="t-scn">—</span><button class="lnk" type="button" id="t-changer">Changer de classeur</button></div></div>
  <div class="empty" id="t-vide"><span class="lab">Module 2 en attente</span><div class="q">Chargez un classeur</div>
    <p>Le module 2 lit uniquement l'affectation retenue par le décideur. Chargez le classeur du module 1 à la station 03.</p>
    <div class="row"><button class="btn" type="button" id="t-vers-c">Aller au classeur</button></div></div>
  <div class="g-side" id="t-plein" hidden>
    <div class="stack" style="gap:20px">
      <div class="pan"><div class="pan-h"><h3>Méthodes</h3><span class="code">TB2-01</span></div><div class="pan-b">
        <div class="meths" id="t-meths"></div>
        <div class="row" style="align-items:end">
          <label class="field" style="flex:1" for="t-limite">Limite (s) / entrepôt<input id="t-limite" type="number" min="1" max="3600"></label>
          <label class="field" style="flex:1" for="t-graine">Graine<input id="t-graine" type="number" min="0"></label></div>
        <div id="t-lancer-zone"></div>
        <p class="hint">Résultats gardés en cache par entrepôt : après une modification de l'affectation, seuls les entrepôts touchés sont recalculés.</p>
      </div></div>
      <div class="pan" id="t-poids-pan" hidden><div class="pan-h"><h3>Compromis</h3><span class="code">TB2-02</span></div><div class="pan-b">
        <div class="slider"><span>Distance</span><input type="range" id="t-poids" min="0" max="1" step="0.05" aria-label="Préférence entre distance et temps"><span>Temps</span></div>
        <p class="hint" id="t-poids-txt"></p>
        <button class="btn" type="button" id="t-appliquer">Appliquer à tous les entrepôts</button>
        <p class="hint">Point du front de référence le plus proche de l'idéal (distance de Tchebycheff pondérée). Vous pouvez ensuite cliquer un autre point.</p>
      </div></div>
    </div>
    <div class="stack" style="gap:20px">
      <div id="t-calc" hidden></div>
      <div class="empty" id="t-pasres"><span class="lab">Fronts non calculés</span><div class="q">Calculez les tournées</div>
        <p id="t-pasres-p"></p></div>
      <div class="stack" id="t-res" style="gap:20px" hidden>
        <div class="whtabs" role="tablist" id="t-tabs"></div>
        <div class="g-wide">
          <div class="pan"><div class="pan-h"><h3>Front de Pareto</h3><span class="code" id="t-front-code"></span></div>
            <div class="pan-b"><svg class="pareto" id="t-pareto" role="img" aria-label="Front de Pareto distance et temps"></svg><div class="leg" id="t-pleg"></div></div></div>
          <div class="pan"><div class="pan-h"><h3>Tournée retenue</h3><span class="code" id="t-origine"></span></div>
            <div class="pan-b"><div class="carte h-s" id="t-carte"></div><p class="hint">Cliquez un magasin pour le confier à un autre entrepôt : un scénario dérivé est créé et seuls les entrepôts touchés sont recalculés.</p></div></div>
        </div>
        <div class="readout" id="t-readout"></div>
        <div class="seq" id="t-seq"></div>
        <div class="pan"><div class="pan-h"><h3>Qualité des fronts · <span id="t-ind-nom"></span></h3><span class="code">TB2-INDICATEURS</span></div>
          <div class="pan-b flush"><div class="scroll"><table class="tbl" id="t-ind"></table></div></div></div>
        <div class="pan"><div class="pan-h"><h3>Synthèse du réseau</h3><span class="code">TB2-SYNTHÈSE</span></div>
          <div class="pan-b flush"><div class="scroll"><table class="tbl" id="t-synth"></table></div></div></div>
        <div class="decide"><span class="lab">Décision</span><div class="q" id="t-q">Valider ces tournées ?</div><p id="t-p"></p>
          <div class="row"><button class="go" type="button" id="t-valider">Valider le plan</button></div></div>
      </div>
    </div>
  </div>`;
  map = carte($('#t-carte', el));
  calc = blocCalcul($('#t-calc', el));
  calc.surStop(async () => { if (S.m2.job) await essayer(() => api(`/api/m2/calcul/${S.m2.job.job_id}/arreter`, { json: {} })); });
  $('#t-changer', el).onclick = () => ctx.aller('classeur');
  $('#t-vers-c', el).onclick = () => ctx.aller('classeur');
  $('#t-meths', el).addEventListener('change', () => { S.m2.choisies = $$('#t-meths input:checked', el).map((i) => i.value); majLancer(); });
  $('#t-limite', el).addEventListener('change', (e) => { S.m2.limite = Math.min(3600, Math.max(1, +e.target.value || 20)); });
  $('#t-graine', el).addEventListener('change', (e) => { S.m2.graine = Math.max(0, parseInt(e.target.value) || 0); });
  $('#t-poids', el).addEventListener('input', (e) => { S.m2.poids = +e.target.value; majPoids(); });
  $('#t-appliquer', el).addEventListener('click', () => { appliquerPoids(); toast('Compromis appliqué à tous les entrepôts.', 'ok'); });
  $('#t-tabs', el).addEventListener('click', (e) => { const b = e.target.closest('[data-e]'); if (b) { S.m2.cur = b.dataset.e; majResultats(); cadrer(); } });
  $('#t-valider', el).addEventListener('click', valider);
}

export function entrer() { majTout(); map.m.invalidateSize(); cadrer(); }
export function recolorer() { if (S.m2.res) { dessinerPareto(); dessinerCarte(); } }

// ---------------------------------------------------------------- scénario
export async function ouvrirScenario(id, { silencieux = false } = {}) {
  const r = await (silencieux ? api(`/api/m2/scenario/${encodeURIComponent(id)}`).catch(() => null)
    : essayer(() => api(`/api/m2/scenario/${encodeURIComponent(id)}`), 'Scénario illisible.'));
  if (!r) return false;
  const change = S.m2.sc?.scenario !== r.scenario;
  S.m2.sc = r; S.scenario = r.scenario;
  if (change) { S.m2.res = null; S.m2.sel = {}; }
  if (!S.m2.cur || !r.tournees.some((t) => t.entrepot === S.m2.cur)) S.m2.cur = r.tournees[0]?.entrepot || null;
  changer(); majTout();
  return true;
}

// ---------------------------------------------------------------- calcul
async function lancer() {
  if (!S.m2.sc || !S.m2.choisies.length) return;
  const r = await essayer(() => api('/api/m2/calcul', { json: { scenario: S.m2.sc.scenario, methodes: S.m2.choisies, limite_temps: S.m2.limite, graine: S.m2.graine } }), 'Calcul refusé.');
  if (!r) return;
  S.m2.job = { job_id: r.job_id, etat: 'en_attente', phase: 'En attente', fraction: 0, ecoule: 0 };
  changer(); majTout();
  clearInterval(minuteur);
  minuteur = setInterval(suivre, 450);
}
async function suivre() {
  if (enVol || !S.m2.job) return;
  enVol = true;
  try {
    const r = await api(`/api/m2/calcul/${S.m2.job.job_id}`).catch(() => null);
    if (!r) { clearInterval(minuteur); S.m2.job = null; toast('Calcul perdu (serveur redémarré ?).', 'err'); changer(); majTout(); return; }
    Object.assign(S.m2.job, r);
    if (r.etat === 'termine' || r.etat === 'erreur' || r.etat === 'arrete') {
      clearInterval(minuteur); S.m2.job = null;
      if (r.etat === 'termine') {
        const prec = S.m2.sel;
        S.m2.res = r.resultat; S.m2.sel = {};
        // garde le choix précédent d'un entrepôt dont la tournée a été reprise du cache
        r.resultat.entrepots.forEach((e) => { const p = prec[e.entrepot]; if (p && !e.recalcules.length && e.resultats[p.k]?.solutions[p.i]) S.m2.sel[e.entrepot] = p; });
        appliquerPoids(true);
        const res = r.resultat;
        toast(`${plural(res.entrepots.length, 'entrepôt')} : ${res.n_recalcules} recalculé${res.n_recalcules > 1 ? 's' : ''}, ${res.n_reutilises} repris du cache · ${sec(res.temps_s)}.`, 'ok', 7000);
        if (res.arrete) toast('Calcul arrêté : fronts partiels.', 'warn');
      } else toast(r.erreur || 'Calcul interrompu.', r.etat === 'erreur' ? 'err' : 'warn', 8000);
      changer();
    }
    majTout();
  } finally { enVol = false; }
}

// ---------------------------------------------------------------- données d'un entrepôt
const service = (n) => S.m2.service * n;
export function points(e) {
  const out = [];
  for (const k of Object.keys(e.resultats)) e.resultats[k].solutions.forEach((s, i) => out.push({ k, i, d: s.distance_km, t: s.temps_min + service(e.n), c: s.temps_min, seq: s.sequence }));
  return out;
}
function reference(e) {
  return (e.indicateurs?.front_reference || []).map((r) => ({ k: r.methode, i: r.index, d: r.distance_km, t: r.temps_min + service(e.n) }));
}
function compromis(pts, w) {
  if (pts.length <= 1) return 0;
  const d = pts.map((p) => p.d), t = pts.map((p) => p.t);
  const [d0, d1, t0, t1] = [Math.min(...d), Math.max(...d), Math.min(...t), Math.max(...t)];
  let best = 0, bv = Infinity;
  pts.forEach((p, j) => {
    const a = (p.d - d0) / ((d1 - d0) || 1), b = (p.t - t0) / ((t1 - t0) || 1);
    const v = Math.max(w * a, (1 - w) * b) + 1e-6 * (a + b);
    if (v < bv) { bv = v; best = j; }
  });
  return best;
}
function appliquerPoids(seulementVides = false) {
  if (!S.m2.res) return;
  S.m2.res.entrepots.forEach((e) => {
    if (seulementVides && S.m2.sel[e.entrepot]) return;
    const ref = reference(e);
    if (!ref.length) { const p = points(e)[0]; if (p) S.m2.sel[e.entrepot] = { k: p.k, i: p.i }; return; }
    const r = ref[compromis(ref, S.m2.poids)];
    S.m2.sel[e.entrepot] = { k: r.k, i: r.i };
  });
  majResultats();
}
const entCourant = () => S.m2.res?.entrepots.find((e) => e.entrepot === S.m2.cur) || S.m2.res?.entrepots[0];
export function solutionChoisie(e) {
  const s = S.m2.sel[e.entrepot];
  const sol = s && e.resultats[s.k]?.solutions[s.i];
  return sol ? { k: s.k, i: s.i, d: sol.distance_km, c: sol.temps_min, t: sol.temps_min + service(e.n), seq: sol.sequence } : null;
}

// ---------------------------------------------------------------- déplacement d'un magasin (révision)
async function deplacer(magasin, vers) {
  map.m.closePopup();
  const r = await essayer(() => api('/api/m2/ajuster', { json: { scenario: S.m2.sc.scenario, magasin, vers } }), 'Déplacement refusé.');
  if (!r) return;
  const prec = S.m2.sel;
  S.m2.sc = r; S.scenario = r.scenario; S.m2.res = null; S.m2.sel = prec;
  toast(`Nouveau scénario ${r.scenario}. Recalcul des entrepôts ${r.ajustements.at(-1).de} et ${r.ajustements.at(-1).vers} seulement.`, 'ok', 7000);
  changer();
  await lancer();
}

// ---------------------------------------------------------------- validation du plan
async function valider() {
  const choix = {};
  for (const e of S.m2.res.entrepots) {
    const s = solutionChoisie(e);
    if (!s) { toast(`Choisissez une tournée pour ${e.entrepot}.`, 'warn'); return; }
    choix[e.entrepot] = { methode: s.k, sequence: s.seq };
  }
  const p = await essayer(() => api('/api/m2/plan', { json: { scenario: S.m2.sc.scenario, choix, enregistrer: true } }), 'Plan refusé.');
  if (!p) return;
  S.plan = p;
  const l = await api('/api/m2/plans').catch(() => null); if (l) S.plans = l.plans;
  toast(`Plan du scénario ${p.scenario} enregistré.`, 'ok');
  changer(); ctx.aller('plan');
}

// ---------------------------------------------------------------- rendu
function majTout() {
  if (!el) return;
  const sc = S.m2.sc;
  $('#t-vide', el).hidden = !!sc; $('#t-plein', el).hidden = !sc;
  if (!sc) return;
  $('#t-scn', el).textContent = `${sc.scenario} · ${plural(sc.n_tournees, 'tournée')}`;
  majMethodes(); majLancer();
  $('#t-limite', el).value = S.m2.limite; $('#t-graine', el).value = S.m2.graine; $('#t-poids', el).value = S.m2.poids; majPoids(false);
  const job = S.m2.job;
  $('#t-calc', el).hidden = !job;
  if (job) calc.maj({ titre: job.phase || 'En attente', detail: `${nf(job.ecoule || 0, 1)} s · ${pct(job.fraction || 0)} · limite ${nf(S.m2.limite)} s par méthode et par entrepôt` });
  $('#t-pasres', el).hidden = !!S.m2.res || !!job;
  $('#t-pasres-p', el).textContent = `${plural(sc.n_tournees, 'entrepôt')} à servir, ${plural(sc.n_magasins, 'magasin')}. Choisissez les méthodes à gauche puis « Calculer ».`;
  $('#t-poids-pan', el).hidden = !S.m2.res;
  majResultats();
}
function majMethodes() {
  const box = $('#t-meths', el), ks = Object.keys(S.m2.methodes);
  if (box.dataset.ok !== String(ks.length)) {
    box.dataset.ok = String(ks.length);
    box.innerHTML = ks.map((k) => { const m = S.m2.methodes[k]; return `<label class="meth" for="tm-${k}"><input type="checkbox" id="tm-${k}" value="${k}">
      <span style="padding-top:3px">${iconeMethode(k)}</span><span><b>${esc(m.nom)}</b><small>${esc(m.famille)} · ${esc(m.ref)}</small></span></label>`; }).join('');
  }
  $$('input', box).forEach((i) => { i.checked = S.m2.choisies.includes(i.value); });
}
function majLancer() {
  const n = S.m2.choisies.length, occupe = !!S.m2.job;
  $('#t-lancer-zone', el).innerHTML = `<button class="${S.m2.res ? 'btn' : 'go'}" type="button" id="t-lancer" ${!n || occupe ? 'disabled' : ''}>
    ${occupe ? 'Calcul en cours…' : S.m2.res ? 'Recalculer les tournées' : 'Calculer les tournées'}</button>`;
  $('#t-lancer', el).onclick = lancer;
}
function majPoids(info = true) {
  const w = S.m2.poids;
  $('#t-poids-txt', el).textContent = w >= 0.95 ? 'Priorité absolue à la distance : la tournée la plus courte.'
    : w <= 0.05 ? 'Priorité absolue au temps : la tournée la plus rapide.'
    : `Poids ${nf(w * 100)} % sur la distance, ${nf((1 - w) * 100)} % sur le temps.`;
  if (info && S.m2.res) appliquerPoids();
}
function majResultats() {
  const res = S.m2.res;
  $('#t-res', el).hidden = !res;
  if (!res) return;
  if (!res.entrepots.some((e) => e.entrepot === S.m2.cur)) S.m2.cur = res.entrepots[0]?.entrepot;
  const idx = Object.fromEntries(S.m2.sc.entrepots.map((e, j) => [e.id, j]));
  $('#t-tabs', el).innerHTML = res.entrepots.map((e) => `<button type="button" role="tab" id="tt-${esc(e.entrepot)}" data-e="${esc(e.entrepot)}" aria-selected="${e.entrepot === S.m2.cur}">
    <span class="sw" style="background:var(--e${(idx[e.entrepot] % 10) + 1})"></span>${esc(e.entrepot)} ${esc(String(e.nom).split(' (')[0])}<small>${e.n} arrêts</small>
    <em class="${e.recalcules.length ? 's-ocre' : 's-gris'}">${e.recalcules.length ? 'recalculé' : 'cache'}</em></button>`).join('');
  const e = entCourant(), s = solutionChoisie(e);
  $('#t-front-code', el).textContent = `${e.entrepot} · ${e.indicateurs?.reference_exacte ? 'RÉFÉRENCE EXACTE' : 'RÉFÉRENCE = MEILLEURS POINTS'}`;
  $('#t-origine', el).textContent = s ? `ORIGINE : ${nomM(s.k).toUpperCase()}` : '';
  $('#t-readout', el).innerHTML = s ? `<div><b>${nf(s.d, 1)} km</b><span>Distance</span></div><div><b>${hm(s.t)}</b><span>Temps total</span></div>
    <div><b>${hm(s.c)}</b><span>Conduite</span></div><div><b>${e.n}</b><span>Arrêts · ${nf(S.m2.service)} min chacun</span></div>` : '';
  const mag = Object.fromEntries(S.m2.sc.magasins.map((m) => [m.id, m]));
  $('#t-seq', el).innerHTML = s ? `<b>Séquence</b> · ${esc(e.entrepot)} → ${s.seq.map((id, r) => `<b>${r + 1}</b> ${esc(mag[id]?.ville || id)}`).join(' → ')} → ${esc(e.entrepot)}` : '';
  // indicateurs
  $('#t-ind-nom', el).textContent = `${e.entrepot}`;
  const ind = e.indicateurs?.methodes || {};
  const meilleurHV = Math.max(...Object.values(ind).map((v) => v.hv_ratio), 0);
  $('#t-ind', el).innerHTML = `<thead><tr><th>Méthode</th><th class="r">Solutions</th><th class="r">Hypervolume</th><th class="r">IGD</th><th class="r">Part du front</th><th class="r">Temps</th><th>Source</th></tr></thead><tbody>
    ${Object.keys(e.resultats).map((k) => { const v = ind[k] || {}, r = e.resultats[k]; return `<tr><td>${iconeMethode(k)} <b style="margin-left:6px">${esc(nomM(k))}</b>${r.stats?.complet ? '<small>front complet prouvé</small>' : ''}</td>
      <td class="r">${nf(v.nb)}</td><td class="r ${v.hv_ratio === meilleurHV ? 'best' : ''}">${pct(v.hv_ratio, 1)}</td><td class="r">${nf(v.igd, 3)}</td><td class="r">${pct(v.contribution)}</td>
      <td class="r">${sec(r.temps_s)}</td><td><span class="st ${e.reutilises.includes(k) ? 's-gris' : 's-ocre'}">${e.reutilises.includes(k) ? 'cache' : 'calculé'}</span></td></tr>`; }).join('')}</tbody>`;
  // synthèse
  let td = 0, tt = 0, tn = 0;
  $('#t-synth', el).innerHTML = `<thead><tr><th>Entrepôt</th><th>Méthode du compromis</th><th class="r">Arrêts</th><th class="r">Distance (km)</th><th class="r">Conduite</th><th class="r">Temps total</th><th>Calcul</th></tr></thead><tbody>
    ${res.entrepots.map((x) => { const c = solutionChoisie(x); if (c) { td += c.d; tt += c.t; } tn += x.n;
      return `<tr class="click ${x.entrepot === S.m2.cur ? 'sel' : ''}" data-e="${esc(x.entrepot)}"><td><span class="sw" style="background:var(--e${(idx[x.entrepot] % 10) + 1})"></span>${esc(x.entrepot)} ${esc(String(x.nom).split(' (')[0])}</td>
      <td>${c ? iconeMethode(c.k) + ' ' + esc(nomM(c.k)) : '—'}</td><td class="r">${x.n}</td><td class="r">${c ? nf(c.d, 1) : '—'}</td><td class="r">${c ? hm(c.c) : '—'}</td><td class="r">${c ? hm(c.t) : '—'}</td>
      <td><span class="st ${x.recalcules.length ? 's-ocre' : 's-gris'}">${x.recalcules.length ? 'recalculé' : 'cache'}</span></td></tr>`; }).join('')}
    <tr class="tot"><td>Réseau</td><td></td><td class="r">${tn}</td><td class="r">${nf(td, 1)}</td><td></td><td class="r">${hm(tt)}</td><td></td></tr></tbody>`;
  $$('#t-synth tr[data-e]', el).forEach((tr) => tr.onclick = () => { S.m2.cur = tr.dataset.e; majResultats(); cadrer(); });
  const valide = S.plan?.scenario === S.m2.sc.scenario;
  $('#t-q', el).textContent = valide ? 'Plan validé' : 'Valider ces tournées ?';
  $('#t-p', el).textContent = `${plural(res.entrepots.length, 'tournée')} · ${nf(td, 1)} km · ${hm(tt)} au total. La validation enregistre le plan de distribution final et ouvre la synthèse.`;
  dessinerPareto(); dessinerCarte();
}

function dessinerPareto() {
  const svg = $('#t-pareto', el), e = entCourant();
  svg.innerHTML = '';
  const W = 560, H = 340, m = { l: 60, r: 16, t: 14, b: 44 };
  svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
  const pts = points(e);
  if (!pts.length) return;
  const [x0, x1] = etendre(Math.min(...pts.map((p) => p.d)), Math.max(...pts.map((p) => p.d)), 0.08);
  const [y0, y1] = etendre(Math.min(...pts.map((p) => p.t)), Math.max(...pts.map((p) => p.t)), 0.1);
  const X = (v) => m.l + (v - x0) / (x1 - x0) * (W - m.l - m.r), Y = (v) => H - m.b - (v - y0) / (y1 - y0) * (H - m.t - m.b);
  const gx = graduations(x0, x1), gy = graduations(y0, y1);
  gx.valeurs.forEach((v) => { sv('line', { x1: X(v), y1: m.t, x2: X(v), y2: H - m.b, class: 'gr' }, svg); sv('text', { x: X(v), y: H - m.b + 15, 'text-anchor': 'middle' }, svg).textContent = nf(v, gx.pas < 1 ? 1 : 0); });
  gy.valeurs.forEach((v) => { sv('line', { x1: m.l, y1: Y(v), x2: W - m.r, y2: Y(v), class: 'gr' }, svg); sv('text', { x: m.l - 6, y: Y(v) + 3, 'text-anchor': 'end' }, svg).textContent = nf(v, gy.pas < 1 ? 1 : 0); });
  sv('line', { x1: m.l, y1: H - m.b, x2: W - m.r, y2: H - m.b, class: 'ax' }, svg); sv('line', { x1: m.l, y1: m.t, x2: m.l, y2: H - m.b, class: 'ax' }, svg);
  sv('text', { x: W - m.r, y: H - 8, 'text-anchor': 'end', class: 'alab' }, svg).textContent = 'Distance totale (km)';
  sv('text', { x: 14, y: m.t + 2, class: 'alab', transform: `rotate(-90 14 ${m.t + 2})`, 'text-anchor': 'end' }, svg).textContent = 'Temps total (min)';
  const ref = reference(e).sort((a, b) => a.d - b.d);
  if (ref.length) { let d = ''; ref.forEach((q, i) => { d += i ? `H${X(q.d)}V${Y(q.t)}` : `M${X(q.d)} ${Y(q.t)}`; }); sv('path', { d, style: 'fill:none;stroke:var(--gris-2);stroke-width:1.2;stroke-dasharray:4 3' }, svg); }
  const s = solutionChoisie(e);
  if (s) {
    sv('line', { x1: m.l, y1: Y(s.t), x2: X(s.d), y2: Y(s.t), style: 'stroke:var(--encre);stroke-dasharray:3 3' }, svg);
    sv('line', { x1: X(s.d), y1: Y(s.t), x2: X(s.d), y2: H - m.b, style: 'stroke:var(--encre);stroke-dasharray:3 3' }, svg);
  }
  const ordre = ['eps', 'pls', 'nsga', 'ws'];
  pts.sort((a, b) => ordre.indexOf(a.k) - ordre.indexOf(b.k)).forEach((p) => {
    const st = STYLE[p.k] || STYLE.eps;
    const g = sv('g', {}, svg);
    forme(g, st.f, X(p.d), Y(p.t), st.c, p.k === 'eps' ? 6 : 5);
    const h = sv('circle', { cx: X(p.d), cy: Y(p.t), r: 9, class: 'hit', tabindex: 0, role: 'button', 'aria-label': `${nomM(p.k)} : ${nf(p.d, 1)} km, ${hm(p.t)}` }, g);
    sv('title', {}, h).textContent = `${nomM(p.k)} · ${nf(p.d, 1)} km · ${hm(p.t)}`;
    const choisir = () => { S.m2.sel[e.entrepot] = { k: p.k, i: p.i }; changer(); majResultats(); };
    h.addEventListener('click', choisir);
    h.addEventListener('keydown', (ev) => { if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); choisir(); } });
  });
  if (s) sv('rect', { x: X(s.d) - 12, y: Y(s.t) - 12, width: 24, height: 24, style: 'fill:none;stroke:var(--encre);stroke-width:2.4;pointer-events:none' }, svg);
  const nb = (k) => e.resultats[k]?.solutions.length || 0;
  $('#t-pleg', el).innerHTML = Object.keys(e.resultats).map((k) => `<span>${iconeMethode(k)}${esc(nomM(k))} · ${nb(k)}</span>`).join('')
    + '<span><svg width="22" height="10" aria-hidden="true"><path d="M1 8 H11 V2 H21" style="fill:none;stroke:var(--gris-2);stroke-dasharray:3 2"/></svg>Front de référence</span>';
}

function cadrer() {
  if (!S.m2.sc || !S.m2.cur) return;
  const ent = S.m2.sc.entrepots.find((x) => x.id === S.m2.cur);
  const pts = S.m2.sc.magasins.filter((x) => x.entrepot === S.m2.cur).map((x) => [x.lat, x.lon]);
  if (ent) pts.push([ent.lat, ent.lon]);
  map.cadrer(pts, 40);
}
function dessinerCarte() {
  if (!S.m2.sc) return;
  map.vider();
  const sc = S.m2.sc, idx = Object.fromEntries(sc.entrepots.map((e, j) => [e.id, j]));
  const e = entCourant(), s = e && solutionChoisie(e);
  sc.magasins.forEach((m) => {
    if (m.entrepot === S.m2.cur) return;
    const mk = L.circleMarker([m.lat, m.lon], { radius: 4, color: css('--carte'), weight: 1, fillColor: couleur(idx[m.entrepot]), fillOpacity: 0.45 }).addTo(map.couche);
    mk.bindTooltip(`${esc(m.ville)} · ${esc(m.entrepot)}`); mk.on('click', () => popup(m));
  });
  sc.entrepots.forEach((x, j) => { if (x.id !== S.m2.cur && x.ouvert) L.marker([x.lat, x.lon], { icon: iconeEntrepot(x.id, couleur(j), true, 20), opacity: 0.55 }).addTo(map.couche); });
  const ent = sc.entrepots.find((x) => x.id === S.m2.cur);
  if (!ent) return;
  const mag = Object.fromEntries(sc.magasins.map((m) => [m.id, m]));
  const c = couleur(idx[ent.id]);
  if (s) {
    const ligne = [[ent.lat, ent.lon], ...s.seq.map((id) => [mag[id].lat, mag[id].lon]), [ent.lat, ent.lon]];
    L.polyline(ligne, { color: css('--encre'), weight: 6, opacity: 0.9, interactive: false }).addTo(map.couche);
    L.polyline(ligne, { color: css('--ocre'), weight: 3.5, opacity: 1, interactive: false }).addTo(map.couche);
    s.seq.forEach((id, r) => {
      const m = mag[id];
      const mk = L.marker([m.lat, m.lon], { icon: iconeArret(r + 1, c), zIndexOffset: 500 }).addTo(map.couche);
      mk.bindTooltip(`<b>${r + 1}. ${esc(m.ville)}</b> · ${esc(m.id)} · ${nf(m.demande)} pal.`); mk.on('click', () => popup(m));
    });
  }
  L.marker([ent.lat, ent.lon], { icon: iconeEntrepot(ent.id, c, true, 28), zIndexOffset: 1000 }).bindTooltip(`<b>${esc(ent.id)} ${esc(ent.nom)}</b>`).addTo(map.couche);
}
function popup(m) {
  const sc = S.m2.sc;
  const div = document.createElement('div'); div.className = 'pop';
  div.innerHTML = `<b>${esc(m.ville)}</b><br><span class="hint">${esc(m.id)} · ${nf(m.demande)} palettes · servi par ${esc(m.entrepot)}</span>
    <div class="lab" style="margin-top:8px">Confier à</div><div class="opts">${sc.entrepots.map((x, k) => {
      const apres = (x.charge + (x.id === m.entrepot ? 0 : m.demande)) / x.capacite, st = etatCapacite(apres);
      return `<button type="button" data-v="${esc(x.id)}" class="${x.id === m.entrepot ? 'cur' : ''}" ${x.id === m.entrepot || apres > 1 + 1e-9 ? 'disabled' : ''}>
        <span><span class="sw" style="background:${couleur(k)}"></span>${esc(x.id)} ${esc(String(x.nom).split(' (')[0])}</span><span class="st ${st[1]}">${pct(apres)}</span></button>`; }).join('')}</div>`;
  div.querySelectorAll('button[data-v]').forEach((b) => b.addEventListener('click', () => deplacer(m.id, b.dataset.v)));
  L.popup({ maxWidth: 320 }).setLatLng([m.lat, m.lon]).setContent(div).openOn(map.m);
}

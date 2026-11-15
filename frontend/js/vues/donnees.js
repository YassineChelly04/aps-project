// Station 01 · Données : source de l'instance, paramètres du calcul, chiffres clés, lecture automatique, carte.
import { S, $, $$, api, changer, nf, esc, essayer, toast, champ, carte, couleur, iconeEntrepot, css, MODELES } from '../core.js';

let el, ctx, map, bandeau;

export function init(racine, c) {
  el = racine; ctx = c;
  el.innerHTML = `
  <div class="banner"><canvas aria-hidden="true"></canvas><div class="c"><div class="plate">
    <div class="w"><svg aria-hidden="true"><use href="#logo"/></svg><b>SIJAR</b></div>
    <i lang="ar">شجر</i><span class="lab">Affecter · Tourner · Décider</span></div></div></div>
  <div class="vhead"><div class="t"><span class="lab">Station 01</span><h2>Préparer l'instance</h2>
    <p>Choisissez le jeu de données et le modèle. Les deux modules travaillent ensuite sur cette instance : affectation des magasins aux entrepôts, puis tournée de chaque entrepôt.</p></div></div>
  <div class="g-side">
    <div class="stack" style="gap:20px">
      <div class="pan"><div class="pan-h"><h3>Source</h3><span class="code">DATA-01</span></div><div class="pan-b">
        <div class="sources" id="d-sources" style="grid-template-columns:1fr"></div>
        <label class="drop" id="d-drop" for="d-fichier"><b>Importer un instance.json</b><span class="hint">Glissez le fichier ici ou cliquez. Format du jeu Tunisie (méta, entrepôts, magasins, coûts).</span></label>
        <input type="file" id="d-fichier" accept=".json,application/json" hidden>
        <p class="hint">Benchmarks OR-Library (cap71 à cap134) et TSPLIB (kroA100, kroB100) : utilisés dans l'expérimentation, voir <span class="mono">donnees_benchmarks/</span>.</p>
      </div></div>
      <div class="pan"><div class="pan-h"><h3>Paramètres du calcul</h3><span class="code">DATA-02</span></div><div class="pan-b">
        <div class="field">Modèle<div class="seg" role="group" aria-label="Modèle" id="d-modele">
          <button type="button" data-v="gap" id="d-mod-gap">GAP</button><button type="button" data-v="sscflp" id="d-mod-ssc">SSCFLP</button></div></div>
        <p class="hint" id="d-modele-txt"></p>
        <div class="row" style="align-items:end">
          <label class="field" style="flex:1" for="d-limite">Limite de temps (s)<input id="d-limite" type="number" min="1" max="3600" step="1"></label>
          <label class="field" style="flex:1" for="d-graine">Graine<input id="d-graine" type="number" min="0" step="1"></label>
        </div>
        <p class="hint">La limite s'applique à chaque méthode. Même graine, mêmes résultats pour les méthodes stochastiques.</p>
      </div></div>
    </div>
    <div class="stack" style="gap:20px">
      <div class="kpis" id="d-kpis"></div>
      <div class="constats" id="d-constats"></div>
      <div class="pan"><div class="pan-h"><h3>Carte de l'instance</h3><span class="code" id="d-region"></span></div>
        <div class="pan-b"><div class="carte" id="d-carte"></div>
        <div class="leg"><span><span class="sw" style="background:var(--encre);border-radius:50%"></span>Magasin (taille = demande)</span><span><span class="sw" style="background:var(--e1)"></span>Entrepôt candidat</span></div></div></div>
    </div>
  </div>
  <div class="decide"><span class="lab">Étape suivante</span><div class="q" id="d-q">Instance prête</div><p id="d-p"></p>
    <div class="row"><button class="go" type="button" id="d-go">Passer à l'affectation</button></div></div>`;

  bandeau = champ($('canvas', el), { mode: 1, k: 9, a: 0.16, sites: [] });
  map = carte($('#d-carte', el));
  $('#d-modele', el).addEventListener('click', (e) => {
    const b = e.target.closest('button'); if (!b) return;
    if (S.modele !== b.dataset.v) { S.modele = b.dataset.v; reinitM1(); changer(); }
    maj();
  });
  $('#d-limite', el).addEventListener('change', (e) => { S.limite = Math.min(3600, Math.max(1, +e.target.value || 30)); changer(); });
  $('#d-graine', el).addEventListener('change', (e) => { S.graine = Math.max(0, parseInt(e.target.value) || 0); changer(); });
  $('#d-sources', el).addEventListener('click', (e) => { const b = e.target.closest('[data-id]'); if (b) chargerParId(b.dataset.id); });
  const fic = $('#d-fichier', el), drop = $('#d-drop', el);
  fic.addEventListener('change', () => { if (fic.files[0]) televerser(fic.files[0]); fic.value = ''; });
  drop.addEventListener('dragover', (e) => { e.preventDefault(); drop.classList.add('over'); });
  drop.addEventListener('dragleave', () => drop.classList.remove('over'));
  drop.addEventListener('drop', (e) => { e.preventDefault(); drop.classList.remove('over'); if (e.dataTransfer.files[0]) televerser(e.dataTransfer.files[0]); });
  $('#d-go', el).addEventListener('click', () => ctx.aller('affectation'));
}

export function reinitM1() {
  Object.assign(S, { jobs: {}, comp: null, choix: null, aff: null, base: null, ind: null, valide: false });
}

function adopter(inst, silencieux) {
  const autre = S.inst?.id !== inst.id;
  S.inst = inst;
  if (autre) reinitM1();
  maj(); changer();
  if (!silencieux) toast(`Instance ${inst.id} chargée : ${inst.n} magasins, ${inst.m} entrepôts.`, 'ok');
}
export async function chargerParId(id, { silencieux = false } = {}) {
  const r = await essayer(() => api('/api/instance', { json: { id } }), 'Instance non chargée.');
  if (r) adopter(r, silencieux);
}
async function televerser(f) {
  const fd = new FormData(); fd.append('fichier', f);
  const r = await essayer(() => api('/api/instance', { form: fd }), 'Import refusé.');
  if (r) adopter(r, false);
}

export function entrer() { map.m.invalidateSize(); if (S.inst) cadrer(); }
export function recolorer() { maj(); }

function cadrer() { map.cadrer([...S.inst.magasins, ...S.inst.entrepots].map((p) => [p.lat, p.lon])); }

function maj() {
  $$('#d-modele button', el).forEach((b) => b.setAttribute('aria-pressed', b.dataset.v === S.modele));
  $('#d-modele-txt', el).textContent = S.modele === 'gap'
    ? 'GAP : tous les entrepôts sont ouverts ; on décide seulement qui sert qui.'
    : 'SSCFLP : l’ouverture des entrepôts est aussi une décision ; leur coût fixe s’ajoute.';
  $('#d-limite', el).value = S.limite; $('#d-graine', el).value = S.graine;
  const tailles = { S: 'Petite', M: 'Moyenne', L: 'Grande' };
  $('#d-sources', el).innerHTML = S.exemples.map((x) => `<button class="src" type="button" data-id="${esc(x.id)}" id="src-${esc(x.taille)}" aria-pressed="${S.inst?.id === x.id}">
    <span class="row" style="justify-content:space-between"><span class="t">${esc(x.taille)}</span><span class="st s-gris">${esc(tailles[x.taille] || '')}</span></span>
    <b>Tunisie · ${esc(x.libelle.split('·')[1] || x.libelle)}</b><small>${esc(x.id)}</small></button>`).join('')
    + (S.inst && !S.exemples.some((x) => x.id === S.inst.id) ? `<button class="src" type="button" aria-pressed="true" data-id="${esc(S.inst.id)}"><b>Instance importée</b><small>${esc(S.inst.id)}</small></button>` : '');
  const i = S.inst;
  if (!i) { $('#d-kpis', el).innerHTML = ''; $('#d-constats', el).innerHTML = ''; $('#d-go', el).disabled = true; return; }
  $('#d-region', el).textContent = i.region || i.id;
  $('#d-kpis', el).innerHTML = i.chiffres_cles.map((k) => `<div class="${k.alerte ? 'al' : ''}"><small>${esc(k.label)}</small><b>${esc(k.value)}</b><span class="sub">${esc(k.sub)}</span></div>`).join('');
  const ton = { alerte: 's-tendu', info: 's-bleu', ok: 's-ok' };
  $('#d-constats', el).innerHTML = i.constats.map((c) => `<div class="constat"><span class="st ${ton[c.ton] || 's-gris'}">${esc(c.tag)}</span><b>${esc(c.titre)}</b><p>${esc(c.texte)}</p></div>`).join('');
  $('#d-q', el).textContent = `${i.id} prête`;
  $('#d-p', el).textContent = `${MODELES[S.modele]} · limite ${nf(S.limite)} s par méthode · graine ${S.graine}.`;
  $('#d-go', el).disabled = false;
  // carte
  map.vider();
  const encre = css('--encre');
  i.magasins.forEach((s) => {
    L.circleMarker([s.lat, s.lon], { radius: 3 + Math.sqrt(s.demande) * 0.8, color: css('--carte'), weight: 1, fillColor: encre, fillOpacity: 0.75 })
      .bindTooltip(`<b>${esc(s.ville)}</b> · ${esc(s.id)}<br>${esc(s.format)} · ${nf(s.demande)} palettes / semaine`).addTo(map.couche);
  });
  i.entrepots.forEach((e, j) => {
    L.marker([e.lat, e.lon], { icon: iconeEntrepot(e.id, couleur(j)), zIndexOffset: 1000 })
      .bindTooltip(`<b>${esc(e.id)} ${esc(e.nom)}</b><br>Capacité ${nf(e.capacite)} palettes${S.modele === 'sscflp' ? ` · coût fixe ${nf(e.cout_fixe)} TND / sem.` : ''}`).addTo(map.couche);
  });
  if (!el.hidden) cadrer();
  // bandeau : les entrepôts de l'instance deviennent les sites du shader
  const la = i.entrepots.map((e) => e.lat), lo = i.entrepots.map((e) => e.lon);
  const [a0, a1, o0, o1] = [Math.min(...la), Math.max(...la), Math.min(...lo), Math.max(...lo)];
  bandeau?.sites(i.entrepots.map((e) => [0.1 + 0.8 * (e.lon - o0) / ((o1 - o0) || 1), 0.15 + 0.7 * (e.lat - a0) / ((a1 - a0) || 1)]));
}

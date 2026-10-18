/* Tableau de bord 1 · Module 1 — reproduit la maquette maquette_dashboard_module1.dc.html.
   Tous les calculs (lecture automatique, indicateurs, titre-conclusion) viennent du backend. */
'use strict';

const LIMITE_TEMPS = 120;   // s par méthode
const SONDAGE_MS = 300;
const WC = ['#2443C4', '#D9822B', '#1E8A6E', '#B8336A', '#6D4CC2', '#2C8FB8', '#8A6D1E', '#C0392B', '#4F6D2E', '#5E6472', '#0F766E', '#9D174D', '#1D4ED8', '#A16207', '#4338CA'];
const NEUTRE = '#A3AAB8';
const FAM = { exacte: ['Exactes', 'optimum prouvé'], heuristique: ['Heuristiques', 'rapides, sans garantie'], metaheuristique: ['Métaheuristiques', 'stochastiques'] };
const TAILLES = [['S', 'Petit · 3 × 20'], ['M', 'Moyen · 5 × 50'], ['L', 'Grand · 10 × 200']];

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const nf = (x, d = 0) => Number(x).toLocaleString('fr-FR', { minimumFractionDigits: d, maximumFractionDigits: d });
const pct = (x, d = 1) => nf(100 * x, d) + ' %';
const pl = (k, mot) => mot + (k > 1 ? 's' : '');

const S = {
  exemples: [], methodes: {}, d: null, importing: false, err: '', modele: 'sscflp',
  runs: {}, comp: null, sel: null, moves: [], mvS: '', mvW: '', ev: null, validated: null, gen: 0,
};

async function api(chemin, opts = {}) {
  const r = await fetch(chemin, opts);
  let corps = null;
  try { corps = await r.json(); } catch (e) { /* corps vide */ }
  if (!r.ok) throw new Error((corps && corps.detail) || ('Erreur ' + r.status));
  return corps;
}
const postJSON = (chemin, data) => api(chemin, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) });

const nomMethode = (k) => S.methodes[k].num + ' ' + S.methodes[k].nom;
const finis = () => Object.keys(S.methodes).filter((k) => S.runs[k] && S.runs[k].etat === 'termine');
const enCours = () => Object.values(S.runs).some((r) => r.etat === 'en_cours' || r.etat === 'en_attente');
const couleur = (j) => WC[j % WC.length];

/* ------------------------------------------------------------------ état */
function reinitialiserCalculs() {
  S.gen++;
  Object.assign(S, { runs: {}, comp: null, sel: null, moves: [], mvS: '', mvW: '', ev: null, validated: null });
}
function frais(d) { reinitialiserCalculs(); Object.assign(S, { d, importing: false, err: '' }); render(); }

async function chargerExemple(t) {
  S.importing = true; S.err = ''; render();
  try { frais(await postJSON('/api/instance', { exemple: t })); }
  catch (e) { S.importing = false; S.err = e.message; render(); }
}
async function chargerFichier(fichier) {
  if (!fichier) return;
  S.importing = true; S.err = ''; render();
  const fd = new FormData(); fd.append('fichier', fichier);
  try { frais(await api('/api/instance', { method: 'POST', body: fd })); }
  catch (e) { S.importing = false; S.err = e.message; render(); }
}
function decharger() { reinitialiserCalculs(); S.d = null; render(); }
function choisirModele(m) { if (S.modele === m || enCours()) return; reinitialiserCalculs(); S.modele = m; render(); }

async function lancer(k) {
  const r = S.runs[k];
  if (r && (r.etat === 'en_cours' || r.etat === 'en_attente')) return;
  const gen = S.gen;
  S.validated = null;
  S.runs[k] = { etat: 'en_attente', phase: 'Envoi…', fraction: 0, ecoule: 0 };
  render();
  try {
    const { job_id } = await postJSON('/api/calcul/' + k, { instance: S.d.id, modele: S.modele, limite_temps: LIMITE_TEMPS });
    if (gen !== S.gen) return;
    S.runs[k].job_id = job_id;
    sonder(k, job_id, gen);
  } catch (e) { if (gen === S.gen) { S.runs[k] = { etat: 'erreur', erreur: e.message }; render(); } }
}

async function sonder(k, jobId, gen) {
  let r;
  try { r = await api('/api/calcul/' + jobId); }
  catch (e) { r = { etat: 'erreur', erreur: e.message }; }
  if (gen !== S.gen || !S.runs[k] || S.runs[k].job_id !== jobId) return;
  Object.assign(S.runs[k], r);
  if (r.etat === 'en_cours' || r.etat === 'en_attente') {
    renderEtapes(); renderE2();
    setTimeout(() => sonder(k, jobId, gen), SONDAGE_MS);
    return;
  }
  if (r.etat === 'termine') {
    if (!S.sel) S.sel = k;
    await rafraichirComparaison(gen);
    await rafraichirEvaluation(gen);
  }
  render();
}

async function rafraichirComparaison(gen) {
  const ids = finis().map((k) => S.runs[k].job_id);
  if (!ids.length) { S.comp = null; return; }
  const c = await postJSON('/api/comparer', { job_ids: ids });
  if (gen === S.gen) S.comp = c;
}

function affectationBase() { return S.sel && S.runs[S.sel] && S.runs[S.sel].resultat ? S.runs[S.sel].resultat.affectation : null; }
function affectationCourante() {
  const base = affectationBase(); if (!base) return null;
  const a = Object.assign({}, base);
  S.moves.forEach((mv) => { a[mv.magasin] = mv.vers; });
  return a;
}
async function rafraichirEvaluation(gen = S.gen) {
  const a = affectationCourante(); if (!a) { S.ev = null; return; }
  const ev = await postJSON('/api/evaluer', { instance: S.d.id, modele: S.modele, affectation: a, meilleur_cout: S.comp ? S.comp.meilleur_cout : null });
  if (gen === S.gen) S.ev = ev;
}
async function apresChangementDecision() { S.validated = null; await rafraichirEvaluation(); renderEtapes(); renderE3(); renderE4(); }

async function valider() {
  const base = affectationBase();
  try {
    S.validated = await postJSON('/api/valider', {
      instance: S.d.id, modele: S.modele, methode: S.sel, affectation: affectationCourante(),
      ajustements: S.moves.map((mv) => ({ magasin: mv.magasin, de: base[mv.magasin], vers: mv.vers })),
    });
  } catch (e) { S.validated = { erreur: e.message }; }
  renderEtapes(); renderE4();
}

/* ------------------------------------------------------------------ rendu */
function render() { renderEtapes(); renderE1(); renderE2(); renderE3(); renderE4(); }

function renderEtapes() {
  const dk = finis().length > 0;
  const faits = [!!S.d, dk, dk && !!S.sel, !!(S.validated && S.validated.scenario)];
  const cur = faits.indexOf(false);
  $('etapes').innerHTML = ['Données', 'Calcul', 'Comparaison', 'Décision'].map((l, i) => {
    const fait = faits[i], actif = i === cur;
    const bg = actif ? '#10141C' : 'transparent', fg = actif ? '#FFFFFF' : (fait ? '#10141C' : '#5A6170');
    const pb = actif ? '#2443C4' : (fait ? '#E3F1EA' : '#E9EBEF'), pf = actif ? '#FFFFFF' : (fait ? '#1E6B45' : '#5A6170');
    return `<li style="background:${bg};color:${fg}" ${actif ? 'aria-current="step"' : ''}><span class="pastille num" style="background:${pb};color:${pf}">${fait ? '✓' : i + 1}</span>${l}</li>`;
  }).join('');
}

function renderE1() {
  const d = S.d, el = $('etape1');
  let h = `<div class="eyebrow">Étape 1 · Données</div>
    <h1 id="t1">${d ? 'Vos données sont chargées' : 'Commencez par importer vos données'}</h1>
    <p class="chapeau">${d ? 'Vérifiez l’instance ci-dessous, puis lancez les méthodes à l’étape 2.' : 'Le tableau de bord compare plusieurs méthodes pour décider quel entrepôt approvisionne chaque magasin. Tout part de votre instance.'}</p>`;
  if (!d) {
    const dispo = new Set(S.exemples.map((x) => x.taille));
    h += `<div id="depot" class="depot">
        <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#2443C4" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"></path><path d="M14 3v5h5"></path><path d="M12 17v-6M9 14l3-3 3 3"></path></svg>
        <div class="depot-titre">${S.importing ? 'Lecture du fichier…' : 'Glissez-déposez votre fichier ici'}</div>
        <div style="font-size:14px;color:#5A6170">Fichier <span class="num">instance.json</span> du jeu « Tunisie » : magasins, entrepôts, capacités et coûts</div>
        <label for="fichier" class="btn btn-primary">Choisir un fichier</label>
        <input id="fichier" class="fichier-cache" type="file" accept=".json,application/json">
        ${S.err ? `<div class="erreur" role="alert">${esc(S.err)}</div>` : ''}
      </div>
      <div class="colonne">
        <div style="font-size:13px;color:#5A6170">Pas de fichier sous la main ? Ouvrez un jeu d'exemple :</div>
        <div class="rangee">${TAILLES.map(([t, l]) => `<button class="chip" data-exemple="${t}" ${!dispo.has(t) || S.importing ? 'disabled' : ''}>${l}</button>`).join('')}</div>
      </div>`;
  } else {
    h += `<div class="charge-ok">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#1E7A4C" stroke-width="2.4" aria-hidden="true"><path d="M5 12l5 5L20 7"></path></svg>
        <span><b class="num">${esc(d.id)}</b> · ${esc(d.region)}</span>
        <button class="chip" id="decharger" style="min-height:36px">Changer de fichier</button>
      </div>
      <div class="grille-kpi">${d.chiffres_cles.map((k) => `<div class="kpi"><div class="kpi-l">${k.label}</div><div class="kpi-v num" style="color:${k.alerte ? '#9A4A0A' : '#10141C'}">${esc(k.value)}</div><div class="kpi-s">${esc(k.sub)}</div></div>`).join('')}</div>
      <div class="grille-constats">${d.constats.map((t) => `<div class="constat"><span class="constat-tag" style="background:${t.bg};color:${t.fg}">${esc(t.tag)}</span><div class="constat-titre">${esc(t.titre)}</div><div class="constat-texte">${esc(t.texte)}</div></div>`).join('')}</div>
      <div class="note">Lecture automatique : constats calculés par règles à partir des chiffres de l'instance.</div>`;
  }
  el.innerHTML = h;
  if (!d) {
    const z = $('depot');
    z.addEventListener('dragover', (e) => { e.preventDefault(); z.classList.add('survol'); });
    z.addEventListener('dragleave', () => z.classList.remove('survol'));
    z.addEventListener('drop', (e) => { e.preventDefault(); z.classList.remove('survol'); chargerFichier(e.dataTransfer && e.dataTransfer.files[0]); });
    $('fichier').addEventListener('change', (e) => chargerFichier(e.target.files && e.target.files[0]));
    el.querySelectorAll('[data-exemple]').forEach((b) => b.addEventListener('click', () => chargerExemple(b.dataset.exemple)));
  } else {
    $('decharger').addEventListener('click', decharger);
  }
}

function tuile(k) {
  const mt = S.methodes[k], r = S.runs[k];
  const etat = !mt.pret ? 'jalon' : (r ? r.etat : 'repos');
  const actif = etat === 'en_cours' || etat === 'en_attente';
  const cls = actif ? 'en-cours' : (etat === 'termine' ? 'fini' : (etat === 'erreur' ? 'echec' : ''));
  const tete = `<span class="num tile-num">${mt.num}</span><span class="tile-nom">${esc(mt.nom)}</span><span class="tile-ref">${esc(mt.ref)}</span>`;
  if (actif) {
    // Pendant le calcul, la tuile n'est plus un bouton : elle contient le bouton « Arrêter ».
    const arretPossible = !!r.job_id && !r.arretDemande;
    return `<div class="tile en-cours" role="group" aria-label="${esc(mt.nom + ', calcul en cours')}">${tete}
      <span class="tile-bas">
        <svg class="spin" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#2443C4" stroke-width="2.4" aria-hidden="true"><path d="M21 12a9 9 0 1 1-6.2-8.6"></path></svg>
        <span class="pulse" style="font-size:12px" aria-live="polite">${esc(r.phase || '')}</span>
        <span class="barre ${etat === 'en_attente' ? 'indet' : ''}"><span style="width:${(100 * (r.fraction || 0)).toFixed(1)}%"></span></span>
        <span class="num petit">${nf(r.ecoule || 0, 1)} s</span>
        <button class="btn-arret" data-arreter="${k}" ${arretPossible ? '' : 'disabled'} aria-label="${esc('Arrêter ' + mt.nom)}">
          <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true"><rect x="1" y="1" width="10" height="10" rx="2" fill="currentColor"></rect></svg>${r.arretDemande ? 'Arrêt…' : 'Arrêter'}</button>
      </span></div>`;
  }
  let bas;
  if (etat === 'jalon') bas = '<span class="badge-gris">Jalon ultérieur</span>';
  else if (etat === 'termine') {
    const res = r.resultat;
    const ecartTxt = res.ecart_borne != null ? 'écart à la borne ' + pct(res.ecart_borne, 2) : (res.arrete ? 'meilleure solution trouvée' : 'limite de temps atteinte');
    const preuve = res.optimal_prouve ? '<span class="prouve">Optimum prouvé</span>'
      : `<span class="non-prouve">${res.arrete ? 'Arrêté · ' : ''}${ecartTxt}</span>`;
    bas = `<span class="num tile-cout">${nf(res.cout_total)}</span><span class="petit">TND / semaine · <span class="num">${nf(res.temps_s, 2)}</span> s</span>${preuve}`;
  } else if (etat === 'erreur') {
    bas = `<span class="erreur">${esc(r.erreur)}</span><span class="lancer">Relancer</span>`;
  } else if (etat === 'arrete') {
    bas = `<span class="non-prouve">${esc(r.erreur || 'Arrêté')}</span><span class="lancer">Relancer</span>`;
  } else bas = '<span class="lancer">Lancer</span>';
  const aria = !mt.pret ? `${mt.nom}, jalon ultérieur` : `Lancer ${mt.nom}`;
  return `<button class="tile ${cls}" data-lancer="${k}" ${!mt.pret ? 'disabled' : ''} aria-label="${esc(aria)}">${tete}
    <span class="tile-bas">${bas}</span></button>`;
}

async function arreter(k) {
  const r = S.runs[k];
  if (!r || !r.job_id || r.arretDemande) return;
  r.arretDemande = true; r.phase = 'Arrêt en cours…';
  renderE2();
  try { await api('/api/calcul/' + r.job_id + '/arreter', { method: 'POST' }); }
  catch (e) { r.arretDemande = false; r.phase = e.message; renderE2(); }
}

function renderE2() {
  const el = $('etape2');
  el.hidden = !S.d;
  if (!S.d) return;
  const ssc = S.modele === 'sscflp', verrou = enCours() ? 'disabled' : '';
  el.innerHTML = `<div class="eyebrow">Étape 2 · Calcul</div>
    <h2 id="t2">Lancez les méthodes</h2>
    <div class="colonne">
      <div class="question" id="q-modele">Peut-on fermer des entrepôts ?</div>
      <div class="segments" role="radiogroup" aria-labelledby="q-modele">
        <button class="seg" role="radio" aria-checked="${!ssc}" data-modele="gap" ${verrou}>Non · tous ouverts (GAP)</button>
        <button class="seg" role="radio" aria-checked="${ssc}" data-modele="sscflp" ${verrou}>Oui · ouverture à décider (SSCFLP)</button>
      </div>
      <div class="aide">${ssc ? 'Le calcul choisit aussi quels entrepôts ouvrir, en payant leur coût fixe (localisation–affectation).' : 'Tous les entrepôts restent ouverts : le calcul décide seulement de l’affectation (affectation généralisée).'}</div>
    </div>
    <div class="grille-familles">${Object.keys(FAM).map((f) => `<div class="famille">
      <div class="colonne" style="gap:2px"><div class="famille-nom">${FAM[f][0]}</div><div class="famille-aide">${FAM[f][1]}</div></div>
      <div class="tuiles">${Object.keys(S.methodes).filter((k) => S.methodes[k].famille === f).map(tuile).join('')}</div></div>`).join('')}</div>`;
  el.querySelectorAll('[data-modele]').forEach((b) => b.addEventListener('click', () => choisirModele(b.dataset.modele)));
  el.querySelectorAll('[data-lancer]').forEach((b) => b.addEventListener('click', () => lancer(b.dataset.lancer)));
  el.querySelectorAll('[data-arreter]').forEach((b) => b.addEventListener('click', () => arreter(b.dataset.arreter)));
}

function renderE3() {
  const el = $('etape3');
  const visible = !!(S.d && S.comp && S.ev);
  el.hidden = !visible;
  if (!visible) return;
  const c = S.comp, d = S.d, ev = S.ev, a = affectationCourante();
  $('t3').textContent = c.titre;
  $('s3-sous').textContent = c.sous_titre;
  $('s3-tableau').innerHTML = `<thead><tr><th>Méthode</th><th>Coût total</th><th>Temps de réponse</th><th>Écart / meilleure</th><th>Entrepôts ouverts</th><th>Taux d'utilisation</th><th>Distance moyenne</th></tr></thead>
    <tbody>${c.lignes.map((b) => `<tr class="${b.termine ? '' : 'inactif'}">
      <td style="font-weight:600">${esc(b.methode)}<div class="td-fam">${esc(b.famille)}</div></td>
      <td class="num" style="font-weight:${b.cout_gras ? 700 : 400}">${esc(b.cout)}</td>
      <td class="num" style="font-weight:${b.temps_gras ? 700 : 400}">${esc(b.temps)}</td>
      <td class="num">${esc(b.ecart)}</td><td class="num">${esc(b.ouverts)}</td><td class="num">${esc(b.utilisation)}</td><td class="num">${esc(b.distance)}</td></tr>`).join('')}</tbody>`;
  $('s3-carte-leg').textContent = 'Solution ' + nomMethode(S.sel) + (S.moves.length ? ' ajustée' : '') + ' · couleur = entrepôt, taille = demande';
  dessinerCarte(d, a, ev);

  const W = d.entrepots;
  const mx = Math.max(1.15, Math.max(...W.map((w, j) => ev.charges[j] / w.capacite)) * 1.05);
  $('s3-charges-leg').textContent = `${ev.entrepots_ouverts} ${pl(ev.entrepots_ouverts, 'entrepôt')} ${pl(ev.entrepots_ouverts, 'ouvert')} · utilisation globale ${pct(ev.taux_utilisation, 0)}`;
  $('s3-charges').innerHTML = W.map((w, j) => {
    const r = ev.charges[j] / w.capacite, ferme = !ev.ouverts[j];
    return `<div class="charge">
      <span class="charge-id"><span class="puce" style="background:${ferme ? NEUTRE : couleur(j)}"></span><b>${esc(w.id)}</b> ${esc(w.nom)}</span>
      <div class="jauge" role="img" aria-label="${esc(w.id)} : ${nf(ev.charges[j])} sur ${nf(w.capacite)} palettes"><div class="rempli" style="width:${(100 * Math.min(r, mx) / mx).toFixed(1)}%;background:${r > 1 ? '#C0392B' : couleur(j)}"></div><div class="cap" style="left:${(100 / mx).toFixed(1)}%"></div></div>
      <span class="num" style="color:${r > 1 ? '#A3261B' : '#3F4552'}">${ferme ? 'fermé' : nf(ev.charges[j]) + ' / ' + nf(w.capacite)}</span></div>`;
  }).join('');
}

/* ------------------------------------------------------------------ carte */
let carte = null, couche = null, carteInstance = null;
function dessinerCarte(d, a, ev) {
  const idx = {}; d.entrepots.forEach((w, j) => { idx[w.id] = j; });
  const conteneur = $('carte');
  if (typeof L === 'undefined') return carteSecours(conteneur, d, a, ev, idx);
  if (!carte) {
    carte = L.map(conteneur, { scrollWheelZoom: false });
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 18, attribution: '© OpenStreetMap' }).addTo(carte);
    couche = L.layerGroup().addTo(carte);
  }
  carte.invalidateSize();
  couche.clearLayers();
  d.magasins.forEach((s) => {
    const j = idx[a[s.id]], w = d.entrepots[j];
    L.polyline([[s.lat, s.lon], [w.lat, w.lon]], { color: couleur(j), weight: 1, opacity: 0.5, interactive: false }).addTo(couche);
  });
  d.magasins.forEach((s) => {
    const j = idx[a[s.id]];
    const z = 6 + Math.sqrt(s.demande) * 0.9;
    L.circleMarker([s.lat, s.lon], { radius: z / 2, color: '#FFFFFF', weight: 1.5, fillColor: couleur(j), fillOpacity: 1 })
      .bindTooltip(`${esc(s.id)} · ${esc(s.ville)} · ${nf(s.demande)} pal./sem. → ${esc(a[s.id])}`).addTo(couche);
  });
  d.entrepots.forEach((w, j) => {
    const o = ev.ouverts[j];
    const html = `<div class="wh-icone"><div class="wh-carre" style="background:${o ? couleur(j) : '#FFFFFF'};opacity:${o ? 1 : 0.5}"></div><span class="wh-label">${esc(w.id)} ${esc(w.nom)}${o ? '' : ' · fermé'}</span></div>`;
    L.marker([w.lat, w.lon], { icon: L.divIcon({ className: '', html, iconSize: [0, 0] }), keyboard: false, zIndexOffset: 1000 }).addTo(couche);
  });
  if (carteInstance !== d.id) {
    const pts = d.magasins.map((s) => [s.lat, s.lon]).concat(d.entrepots.map((w) => [w.lat, w.lon]));
    carte.fitBounds(pts, { padding: [30, 30] });
    carteInstance = d.id;
  }
}

function carteSecours(conteneur, d, a, ev, idx) {
  // Sans Leaflet (hors ligne) : projection équirectangulaire simple, comme la maquette.
  const lats = d.magasins.map((s) => s.lat).concat(d.entrepots.map((w) => w.lat));
  const lons = d.magasins.map((s) => s.lon).concat(d.entrepots.map((w) => w.lon));
  const la0 = Math.min(...lats), la1 = Math.max(...lats), lo0 = Math.min(...lons), lo1 = Math.max(...lons);
  const cphi = Math.cos((la0 + la1) / 2 * Math.PI / 180);
  const sx = Math.max((lo1 - lo0) * cphi, 0.05), sy = Math.max(la1 - la0, 0.05);
  const sc = Math.min(470 / sx, 520 / sy), pad = 36;
  const px = (lo) => (lo - lo0) * cphi * sc + pad, py = (la) => (la1 - la) * sc + pad;
  const W = sx * sc + 2 * pad, H = sy * sc + 2 * pad;
  let g = '';
  d.magasins.forEach((s) => { const w = d.entrepots[idx[a[s.id]]]; g += `<line x1="${px(s.lon)}" y1="${py(s.lat)}" x2="${px(w.lon)}" y2="${py(w.lat)}" stroke="${couleur(idx[a[s.id]])}" stroke-opacity=".5"/>`; });
  d.magasins.forEach((s) => { const z = 6 + Math.sqrt(s.demande) * 0.9; g += `<circle cx="${px(s.lon)}" cy="${py(s.lat)}" r="${z / 2}" fill="${couleur(idx[a[s.id]])}" stroke="#fff" stroke-width="1.5"><title>${esc(s.id)} · ${esc(s.ville)} · ${nf(s.demande)} pal./sem. → ${esc(a[s.id])}</title></circle>`; });
  d.entrepots.forEach((w, j) => {
    const o = ev.ouverts[j], x = px(w.lon), y = py(w.lat);
    g += `<rect x="${x - 8}" y="${y - 8}" width="16" height="16" rx="4" fill="${o ? couleur(j) : '#fff'}" stroke="#10141C" stroke-width="2" opacity="${o ? 1 : 0.5}"/>
      <text x="${x}" y="${y + 22}" text-anchor="middle" font-size="11" font-weight="700" font-family="IBM Plex Sans, sans-serif" fill="#10141C" paint-order="stroke" stroke="#fff" stroke-width="3">${esc(w.id)} ${esc(w.nom)}${o ? '' : ' · fermé'}</text>`;
  });
  conteneur.innerHTML = `<svg viewBox="0 0 ${W.toFixed(0)} ${H.toFixed(0)}" width="100%" height="100%" preserveAspectRatio="xMidYMid meet">${g}</svg>`;
}

/* ------------------------------------------------------------------ étape 4 */
function renderE4() {
  const el = $('etape4');
  const visible = !!(S.d && S.comp && S.ev);
  el.hidden = !visible;
  if (!visible) return;
  const d = S.d, ev = S.ev, base = affectationBase(), a = affectationCourante();
  const parId = {}; d.magasins.forEach((s) => { parId[s.id] = s; });
  const g = S.comp.meilleur_cout ? (ev.cout_total - S.comp.meilleur_cout) / S.comp.meilleur_cout : 0;
  const v = S.validated;
  el.innerHTML = `<div class="eyebrow">Étape 4 · Décision</div>
    <h2 id="t4">Choisissez l'affectation à transmettre</h2>
    <div class="rangee" role="radiogroup" aria-label="Affectation retenue" style="gap:10px">${finis().map((k) => {
      const res = S.runs[k].resultat;
      return `<button class="btn choix" role="radio" aria-checked="${S.sel === k}" data-choix="${k}"><span>${esc(nomMethode(k))}</span><span class="num sous">${nf(res.cout_total)} TND/sem. · ${nf(res.temps_s, 2)} s</span></button>`;
    }).join('')}</div>
    <div class="ajust">
      <div class="ajust-titre">Ajustement manuel (facultatif)</div>
      <div class="champs">
        <div class="champ"><label for="mvs">Magasin</label><select id="mvs"><option value="">Choisir un magasin</option>${d.magasins.map((s) => `<option value="${esc(s.id)}" ${S.mvS === s.id ? 'selected' : ''}>${esc(s.id)} · ${esc(s.ville)} · ${nf(s.demande)} pal. → ${esc(a[s.id])}</option>`).join('')}</select></div>
        <div class="champ"><label for="mvw">Nouvel entrepôt</label><select id="mvw"><option value="">Choisir un entrepôt</option>${d.entrepots.map((w, j) => `<option value="${esc(w.id)}" ${S.mvW === w.id ? 'selected' : ''}>${esc(w.id)} ${esc(w.nom)} · reste ${nf(w.capacite - ev.charges[j])}</option>`).join('')}</select></div>
      </div>
      <div class="rangee">
        <button class="btn btn-ghost" id="reaffecter" ${S.mvS && S.mvW ? '' : 'disabled'}>Réaffecter</button>
        <button class="btn btn-ghost" id="annuler" ${S.moves.length ? '' : 'disabled'}>Annuler les ajustements</button>
      </div>
      ${S.moves.map((mv) => `<div class="num" style="font-size:12px;color:#3F4552">${esc(mv.magasin)} (${esc(parId[mv.magasin].ville)}) : ${esc(base[mv.magasin])} → ${esc(mv.vers)}</div>`).join('')}
      <div class="bilan" aria-live="polite">
        <span>Coût : <b class="num">${nf(ev.cout_total)} TND/sem.</b></span>
        <span>Écart / optimum : <b class="num" style="color:${g > 0.0001 ? '#9A4A0A' : '#1E6B45'}">+${pct(g, 2)}</b></span>
        <span>Capacités : <b style="color:${ev.realisable ? '#1E6B45' : '#A3261B'}">${ev.realisable ? 'respectées' : 'dépassées'}</b></span>
      </div>
    </div>
    <button class="btn btn-primary btn-grand" id="valider" ${!ev.realisable || (v && v.scenario) ? 'disabled' : ''}>Valider et transmettre au module 2</button>
    ${v && v.scenario ? `<div class="valide" role="status"><b>Affectation validée · scénario <span class="num">${esc(v.scenario)}</span></b>
        <span class="num">${esc(v.fichier)} · ${v.n_magasins} magasins · ${v.n_ouverts} ${pl(v.n_ouverts, 'entrepôt')}</span>
        <span>Prête pour le module 2 (jalon ultérieur).</span></div>` : ''}
    ${v && v.erreur ? `<div class="erreur" role="alert">${esc(v.erreur)}</div>` : ''}`;

  el.querySelectorAll('[data-choix]').forEach((b) => b.addEventListener('click', () => { S.sel = b.dataset.choix; apresChangementDecision(); }));
  $('mvs').addEventListener('change', (e) => { S.mvS = e.target.value; $('reaffecter').disabled = !(S.mvS && S.mvW); });
  $('mvw').addEventListener('change', (e) => { S.mvW = e.target.value; $('reaffecter').disabled = !(S.mvS && S.mvW); });
  $('reaffecter').addEventListener('click', () => {
    const s = S.mvS, w = S.mvW;
    S.moves = S.moves.filter((x) => x.magasin !== s);
    if (base[s] !== w) S.moves.push({ magasin: s, vers: w });
    S.mvS = ''; S.mvW = '';
    apresChangementDecision();
  });
  $('annuler').addEventListener('click', () => { S.moves = []; apresChangementDecision(); });
  $('valider').addEventListener('click', valider);
}

/* ------------------------------------------------------------------ démarrage */
api('/api/exemples').then((x) => { S.exemples = x.exemples; S.methodes = x.methodes; render(); })
  .catch((e) => { S.err = 'Serveur injoignable : ' + e.message; render(); });
render();

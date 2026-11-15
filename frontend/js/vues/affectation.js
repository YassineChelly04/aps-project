// Station 02 · Tableau de bord 1 : lancer les méthodes, comparer, retenir, ajuster à la main, valider.
import { S, $, $$, api, changer, nf, pct, sec, esc, essayer, toast, carte, couleur, iconeEntrepot, css, etatCapacite,
  blocCalcul, sv, etendre, graduations, MODELES, plural } from '../core.js';
import { rafraichir as rafraichirClasseur } from './classeur.js';

let el, ctx, map, calc, minuteur = null;
const FAMILLES = [['exacte', 'Exactes'], ['heuristique', 'Heuristiques'], ['metaheuristique', 'Métaheuristiques']];
const actifs = () => Object.entries(S.jobs).filter(([, j]) => j.etat === 'en_attente' || j.etat === 'en_cours');
const nomM = (k) => `${S.methodes[k]?.num || ''} ${S.methodes[k]?.nom || k}`;

export function init(racine, c) {
  el = racine; ctx = c;
  el.innerHTML = `
  <div class="vhead"><div class="t"><span class="lab">Station 02 · Tableau de bord 1</span><h2>Affecter les magasins</h2>
    <p>Lancez les méthodes, comparez-les sur les mêmes indicateurs, retenez une affectation. Cliquez un magasin sur la carte pour le confier à un autre entrepôt.</p></div>
    <span class="chip" id="a-param"></span></div>
  <div class="g-side">
    <div class="stack" style="gap:20px">
      <div class="pan"><div class="pan-h"><h3>Méthodes</h3><span class="code">TB1-01</span></div><div class="pan-b">
        <div class="meths" id="a-meths"></div>
        <div id="a-lancer-zone"></div>
      </div></div>
      <div class="pan" id="a-jobs-pan" hidden><div class="pan-h"><h3>File de calcul</h3><span class="code">TB1-02</span></div><div class="pan-b"><div class="jobs" id="a-jobs"></div></div></div>
    </div>
    <div class="stack" style="gap:20px">
      <div id="a-calc" hidden></div>
      <div class="empty" id="a-vide"><span class="lab">Aucun résultat</span><div class="q">Lancez les méthodes</div>
        <p>Choisissez au moins une méthode à gauche, puis « Lancer ». Les calculs passent un par un ; chaque méthode respecte la limite de temps.</p></div>
      <div class="stack" id="a-res" style="gap:20px" hidden>
        <div class="pan"><div class="pan-h"><h3 id="a-titre"></h3><span class="code">TB1-COMPARAISON</span></div>
          <div class="pan-b" style="gap:10px"><p class="muted" id="a-sous" style="font-size:14px"></p>
          <div class="scroll"><table class="tbl" id="a-table"></table></div>
          <p class="hint">Cliquez une ligne pour afficher cette affectation. Souligné en jaune : meilleure valeur de la colonne.</p></div></div>
        <div class="kpis k6" id="a-kpis"></div>
        <div class="g2">
          <div class="pan"><div class="pan-h"><h3>Image de l'affectation</h3><span class="code">TB1-CARTE</span></div>
            <div class="pan-b"><div class="carte" id="a-carte"></div><div class="leg" id="a-leg"></div></div></div>
          <div class="stack" style="gap:20px">
            <div class="pan"><div class="pan-h"><h3>Charge / capacité</h3><span class="code">TB1-CHARGE</span></div>
              <div class="pan-b"><div class="gauges" id="a-charges"></div><p class="hint">Trait noir : seuil de tension à 85 %.</p></div></div>
            <div class="pan"><div class="pan-h"><h3>Convergence</h3><span class="code">TB1-TEMPS</span></div>
              <div class="pan-b"><svg class="conv" id="a-conv" role="img" aria-label="Meilleur coût trouvé au cours du temps"></svg><div class="leg" id="a-conv-leg"></div></div></div>
          </div>
        </div>
        <div class="pan" id="a-ajust-pan" hidden><div class="pan-h"><h3>Modifications manuelles</h3><span class="code">TB1-AJUST</span></div>
          <div class="pan-b flush"><div class="scroll"><table class="tbl" id="a-ajust"></table></div></div></div>
        <div class="decide"><span class="lab">Décision</span><div class="q" id="a-q"></div><p id="a-p"></p>
          <div class="row"><button class="btn" type="button" id="a-annuler">Annuler les modifications</button>
          <button class="go" type="button" id="a-valider">Valider et créer le classeur</button></div></div>
      </div>
    </div>
  </div>`;
  map = carte($('#a-carte', el));
  calc = blocCalcul($('#a-calc', el));
  calc.surStop(() => { const run = actifs().find(([, j]) => j.etat === 'en_cours'); if (run) arreter(run[0]); });
  $('#a-meths', el).addEventListener('change', (e) => {
    if (e.target.name !== 'meth') return;
    S.choisies = $$('#a-meths input:checked', el).map((i) => i.value); majLancer(); changer();
  });
  $('#a-jobs', el).addEventListener('click', (e) => { const b = e.target.closest('[data-stop]'); if (b) arreter(b.dataset.stop); });
  $('#a-table', el).addEventListener('click', (e) => { const tr = e.target.closest('tr[data-k]'); if (tr) choisir(tr.dataset.k); });
  $('#a-annuler', el).addEventListener('click', async () => { S.aff = { ...S.base }; await evaluer(); });
  $('#a-valider', el).addEventListener('click', valider);
}

export function entrer() { majTout(); map.m.invalidateSize(); if (S.inst && S.aff) cadrer(); }
export function recolorer() { if (S.aff) dessinerCarte(); dessinerConvergence(); }

// ---------------------------------------------------------------- lancement et suivi
async function lancer() {
  if (!S.inst || !S.choisies.length) return;
  S.jobs = {}; S.comp = null; S.choix = null; S.aff = null; S.base = null; S.ind = null; S.valide = false;
  for (const k of Object.keys(S.methodes).filter((k) => S.choisies.includes(k) && S.methodes[k].pret)) {
    const r = await essayer(() => api(`/api/calcul/${k}`, { json: { instance: S.inst.id, modele: S.modele, limite_temps: S.limite, graine: S.graine } }),
      `${nomM(k)} :`);
    if (r) S.jobs[k] = { job_id: r.job_id, etat: 'en_attente', phase: 'En attente', fraction: 0, ecoule: 0 };
  }
  changer(); majTout(); suivre();
}
function suivre() {
  clearInterval(minuteur);
  let enVol = false;
  minuteur = setInterval(async () => {
    if (enVol) return;
    enVol = true;
    try {
      const a = actifs();
      if (!a.length) { clearInterval(minuteur); minuteur = null; await comparer(); return; }
      for (const [k, j] of a) {
        const r = await api(`/api/calcul/${j.job_id}`).catch(() => null);
        if (!r) { Object.assign(j, { etat: 'erreur', erreur: 'Calcul perdu (serveur redémarré ?)' }); continue; }
        Object.assign(j, r);
        if (r.etat === 'erreur') toast(`${nomM(k)} : ${r.erreur}`, 'err', 9000);
      }
      majCalcul(); majJobs(); majLancer(); changer();
    } finally { enVol = false; }
  }, 450);
}
async function arreter(k) {
  const j = S.jobs[k]; if (!j) return;
  await essayer(() => api(`/api/calcul/${j.job_id}/arreter`, { json: {} }));
}
async function comparer() {
  const ok = Object.values(S.jobs).filter((j) => j.etat === 'termine');
  majCalcul(); majJobs();
  if (!ok.length) { changer(); majTout(); return; }
  const c = await essayer(() => api('/api/comparer', { json: { job_ids: ok.map((j) => j.job_id) } }), 'Comparaison impossible.');
  if (!c) return;
  S.comp = c;
  const meilleure = c.lignes.find((l) => l.termine && l.cout_gras) || c.lignes.find((l) => l.termine);
  if (meilleure) choisir(meilleure.cle, { silencieux: true });
  toast(c.titre, 'ok', 7000);
}

// ---------------------------------------------------------------- choix et ajustements
function choisir(k, { silencieux } = {}) {
  const j = S.jobs[k];
  if (!j?.resultat) return;
  if (S.choix && S.choix !== k && Object.keys(ajustements()).length && !silencieux) toast('Modifications manuelles abandonnées.', 'warn');
  S.choix = k; S.base = { ...j.resultat.affectation }; S.aff = { ...S.base };
  S.ind = { ...j.resultat.indicateurs }; S.valide = false;
  changer(); majTout(); cadrer();
}
function ajustements() {
  const out = {};
  if (!S.aff) return out;
  for (const m in S.aff) if (S.aff[m] !== S.base[m]) out[m] = { magasin: m, de: S.base[m], vers: S.aff[m] };
  return out;
}
async function deplacer(magasin, vers) {
  map.m.closePopup();
  S.aff[magasin] = vers; S.valide = false;
  await evaluer();
}
async function evaluer() {
  const r = await essayer(() => api('/api/evaluer', { json: { instance: S.inst.id, modele: S.modele, affectation: S.aff, meilleur_cout: S.comp?.meilleur_cout } }));
  if (r) S.ind = r;
  changer(); majTout();
}
async function valider() {
  const aj = Object.values(ajustements());
  const r = await essayer(() => api('/api/valider', { json: { instance: S.inst.id, modele: S.modele, methode: S.choix, affectation: S.aff, ajustements: aj } }), 'Validation refusée.');
  if (!r) return;
  S.scenario = r.scenario; S.valide = true;
  toast(`Affectation validée : scénario ${r.scenario}. Le classeur Excel est prêt.`, 'ok', 7000);
  await rafraichirClasseur();
  changer(); ctx.aller('classeur');
}

// ---------------------------------------------------------------- rendu
function majTout() {
  if (!el) return;
  $('#a-param', el).textContent = S.inst ? `${S.inst.id} · ${S.modele.toUpperCase()} · ${nf(S.limite)} s · graine ${S.graine}` : 'Aucune instance';
  majMethodes(); majLancer(); majJobs(); majCalcul(); majResultats();
}
function majMethodes() {
  const box = $('#a-meths', el);
  if (box.dataset.ok === String(Object.keys(S.methodes).length)) { $$('input', box).forEach((i) => { i.checked = S.choisies.includes(i.value); }); return; }
  box.dataset.ok = String(Object.keys(S.methodes).length);
  box.innerHTML = FAMILLES.map(([f, lib]) => `<div class="fam"><span class="lab">${lib}</span>${Object.entries(S.methodes).filter(([, m]) => m.famille === f).map(([k, m]) => `
    <label class="meth" for="m-${k}"><input type="checkbox" name="meth" id="m-${k}" value="${k}" ${S.choisies.includes(k) ? 'checked' : ''} ${m.pret ? '' : 'disabled'}>
      <span class="n">${esc(m.num)}</span><span><b>${esc(m.nom)}</b><small>${esc(m.ref)}${m.stochastique ? ' · stochastique' : ''}</small></span></label>`).join('')}</div>`).join('');
}
function majLancer() {
  const n = S.choisies.filter((k) => S.methodes[k]?.pret).length;
  const occupe = actifs().length > 0;
  const primaire = !S.comp;
  $('#a-lancer-zone', el).innerHTML = `<button class="${primaire ? 'go' : 'btn'}" type="button" id="a-lancer" ${!S.inst || !n || occupe ? 'disabled' : ''}>
    ${occupe ? 'Calcul en cours…' : S.comp ? `Relancer ${plural(n, 'méthode')}` : `Lancer ${plural(n, 'méthode')}`}</button>`;
  $('#a-lancer', el).onclick = lancer;
}
function majJobs() {
  const ent = Object.entries(S.jobs);
  $('#a-jobs-pan', el).hidden = !ent.length;
  const lib = { en_attente: 'En attente', en_cours: 'En cours', termine: 'Terminé', arrete: 'Arrêté', erreur: 'Erreur' };
  $('#a-jobs', el).innerHTML = ent.map(([k, j]) => {
    const cours = j.etat === 'en_cours' || j.etat === 'en_attente';
    const info = j.etat === 'termine' ? `${nf(j.resultat.cout_total)} TND · ${sec(j.resultat.temps_s)}` : j.etat === 'en_cours' ? `${esc(j.phase)} · ${sec(j.ecoule)}` : esc(j.erreur || lib[j.etat]);
    return `<div class="job"><span class="n">${esc(S.methodes[k]?.num)}</span><div><b style="font-size:14px">${esc(S.methodes[k]?.nom)}</b><br><small>${info}</small>
      ${cours ? `<div class="bar-p"><i style="width:${Math.round((j.fraction || 0) * 100)}%"></i></div>` : ''}</div>
      ${cours ? `<button class="btn sm" type="button" data-stop="${k}">Arrêter</button>` : `<span class="st ${j.etat === 'termine' ? 's-ok' : j.etat === 'erreur' ? 's-dep' : 's-tendu'}">${lib[j.etat]}</span>`}</div>`;
  }).join('');
}
function majCalcul() {
  const a = actifs();
  $('#a-calc', el).hidden = !a.length;
  if (!a.length) return;
  const run = a.find(([, j]) => j.etat === 'en_cours');
  const total = Object.keys(S.jobs).length, fini = total - a.length;
  calc.maj(run ? { titre: `${nomM(run[0])}`, detail: `${run[1].phase} · ${nf(run[1].ecoule, 1)} s / ${nf(S.limite)} s · méthode ${fini + 1} sur ${total}` }
    : { titre: 'En attente', detail: 'Le serveur termine un calcul précédent.' });
}
function majResultats() {
  const a = actifs().length;
  $('#a-vide', el).hidden = !!S.comp || a > 0;
  $('#a-res', el).hidden = !S.comp;
  if (!S.comp) return;
  $('#a-titre', el).textContent = S.comp.titre;
  $('#a-sous', el).textContent = S.comp.sous_titre;
  $('#a-table', el).innerHTML = `<thead><tr><th></th><th>Méthode</th><th class="r">Coût (TND/sem.)</th><th class="r">Temps</th><th class="r">Écart</th>
    <th class="r">Ouverts</th><th class="r">Utilisation</th><th class="r">Dist. moy.</th><th>Garantie</th></tr></thead><tbody>${S.comp.lignes.filter((l) => l.termine || S.jobs[l.cle]).map((l) => `
    <tr class="${l.termine ? 'click' : ''} ${l.cle === S.choix ? 'sel' : ''}" ${l.termine ? `data-k="${l.cle}"` : ''}>
      <td><input type="radio" name="a-choix" id="a-r-${l.cle}" ${l.cle === S.choix ? 'checked' : ''} ${l.termine ? '' : 'disabled'} aria-label="Retenir ${esc(l.methode)}"></td>
      <td><b>${esc(l.methode)}</b><small>${esc(l.famille)}</small></td>
      <td class="r ${l.cout_gras ? 'best' : ''}">${esc(l.cout)}</td><td class="r ${l.temps_gras ? 'best' : ''}">${esc(l.temps)}</td>
      <td class="r">${esc(l.ecart)}</td><td class="r">${esc(l.ouverts)}</td><td class="r">${esc(l.utilisation)}</td><td class="r">${esc(l.distance)}</td>
      <td>${l.termine ? `<span class="st ${/optimum/.test(l.garantie) ? 's-ok' : /borne/.test(l.garantie) ? 's-bleu' : 's-gris'}">${esc(l.garantie.split(' · ')[0])}</span>` : `<span class="st s-dep">${esc(l.cout)}</span>`}</td></tr>`).join('')}</tbody>`;
  if (!S.ind) return;
  const i = S.ind, aj = Object.values(ajustements());
  const meil = S.comp.meilleur_cout;
  const ecartV = meil ? (i.cout_total - meil) / meil : 0;
  const tps = S.jobs[S.choix]?.resultat?.temps_s;
  $('#a-kpis', el).innerHTML = `
    <div><small>Coût total</small><b>${nf(i.cout_total)}</b><span class="sub">TND / semaine${i.cout_fixe ? ` · dont fixe ${nf(i.cout_fixe)}` : ''}</span></div>
    <div><small>Écart à la meilleure</small><b>${pct(ecartV, 2)}</b><span class="sub">${aj.length ? 'après modifications' : esc(nomM(S.choix))}</span></div>
    <div><small>Entrepôts ouverts</small><b>${i.entrepots_ouverts} / ${i.m}</b><span class="sub">${MODELES[S.modele].split(' (')[0]}</span></div>
    <div class="${i.taux_utilisation > 0.95 ? 'al' : ''}"><small>Utilisation</small><b>${pct(i.taux_utilisation)}</b><span class="sub">capacité ouverte</span></div>
    <div><small>Distance moyenne</small><b>${nf(i.distance_moyenne, 1)} km</b><span class="sub">magasin–entrepôt</span></div>
    <div><small>Temps de réponse</small><b>${sec(tps)}</b><span class="sub">méthode retenue</span></div>`;
  // charges
  $('#a-charges', el).innerHTML = S.inst.entrepots.map((e, j) => {
    const u = i.charges[j] / e.capacite, st = etatCapacite(u), ouvert = i.ouverts[j];
    return `<div class="gauge ${ouvert ? '' : 'ferme'}"><span title="${esc(e.nom)}"><span class="sw" style="background:var(--e${(j % 10) + 1})"></span>${esc(e.id)} ${esc(e.nom)}</span>
      <div class="b"><i style="width:${Math.min(u, 1) * 100}%;background:var(${st[2]})"></i><u></u></div>
      <span class="st ${ouvert ? st[1] : 's-gris'}">${ouvert ? `${nf(i.charges[j])}/${nf(e.capacite)} · ${pct(u)}` : 'Fermé'}</span></div>`;
  }).join('');
  // ajustements
  $('#a-ajust-pan', el).hidden = !aj.length;
  const nomE = (id) => S.inst.entrepots.find((e) => e.id === id)?.nom || id;
  const mag = Object.fromEntries(S.inst.magasins.map((s) => [s.id, s]));
  $('#a-ajust', el).innerHTML = `<thead><tr><th>Magasin</th><th>De</th><th>Vers</th><th class="r">Demande</th><th></th></tr></thead><tbody>${aj.map((a) => `
    <tr><td><b>${esc(mag[a.magasin]?.ville)}</b><small>${esc(a.magasin)}</small></td><td>${esc(a.de)} ${esc(nomE(a.de))}</td><td>${esc(a.vers)} ${esc(nomE(a.vers))}</td>
    <td class="r">${nf(mag[a.magasin]?.demande)}</td><td><button class="btn sm" type="button" data-retour="${esc(a.magasin)}">Rétablir</button></td></tr>`).join('')}</tbody>`;
  $$('[data-retour]', el).forEach((b) => b.onclick = () => deplacer(b.dataset.retour, S.base[b.dataset.retour]));
  // décision
  $('#a-q', el).textContent = S.valide ? 'Affectation validée' : aj.length ? 'Valider l’affectation modifiée ?' : `Valider l'affectation ${nomM(S.choix)} ?`;
  $('#a-p', el).textContent = !i.realisable
    ? 'Une capacité est dépassée : déplacez un magasin vers un entrepôt disponible avant de valider.'
    : S.valide ? `Scénario ${S.scenario}. Le classeur est prêt à la station 03.`
    : `${aj.length ? plural(aj.length, 'magasin déplacé', 'magasins déplacés') + ' à la main. ' : ''}La validation écrit le fichier d'échange et le classeur Excel du scénario.`;
  $('#a-valider', el).disabled = !i.realisable || S.valide;
  $('#a-annuler', el).disabled = !aj.length;
  dessinerCarte(); dessinerConvergence();
}

function cadrer() { if (S.inst) map.cadrer([...S.inst.magasins, ...S.inst.entrepots].map((p) => [p.lat, p.lon])); }
function dessinerCarte() {
  if (!S.aff || !S.ind) return;
  map.vider();
  const idx = Object.fromEntries(S.inst.entrepots.map((e, j) => [e.id, j]));
  const ent = S.inst.entrepots, ch = S.ind.charges;
  const aj = ajustements();
  S.inst.magasins.forEach((s) => {
    const j = idx[S.aff[s.id]], e = ent[j], c = couleur(j);
    L.polyline([[s.lat, s.lon], [e.lat, e.lon]], { color: c, weight: 1.4, opacity: 0.65, interactive: false }).addTo(map.couche);
    if (aj[s.id]) L.circleMarker([s.lat, s.lon], { radius: 11, color: css('--encre'), weight: 1.5, dashArray: '3 3', fill: false, interactive: false }).addTo(map.couche);
    const mk = L.circleMarker([s.lat, s.lon], { radius: 3.5 + Math.sqrt(s.demande) * 0.75, color: css('--carte'), weight: 1.5, fillColor: c, fillOpacity: 0.95 }).addTo(map.couche);
    mk.bindTooltip(`<b>${esc(s.ville)}</b> · ${nf(s.demande)} pal. · ${esc(e.id)}`);
    mk.on('click', () => {
      const opts = ent.map((x, k) => {
        const apres = (ch[k] + (k === j ? 0 : s.demande)) / x.capacite;
        const st = etatCapacite(apres);
        return `<button type="button" data-v="${esc(x.id)}" class="${k === j ? 'cur' : ''}" ${k === j ? 'disabled' : ''}>
          <span><span class="sw" style="background:${couleur(k)}"></span>${esc(x.id)} ${esc(x.nom)}</span><span class="st ${st[1]}">${pct(apres)}</span></button>`;
      }).join('');
      const div = document.createElement('div'); div.className = 'pop';
      div.innerHTML = `<b>${esc(s.ville)}</b><br><span class="hint">${esc(s.id)} · ${nf(s.demande)} palettes / semaine</span>
        <div class="lab" style="margin-top:8px">Confier à</div><div class="opts">${opts}</div>`;
      div.querySelectorAll('button[data-v]').forEach((b) => b.addEventListener('click', () => deplacer(s.id, b.dataset.v)));
      L.popup({ maxWidth: 320 }).setLatLng([s.lat, s.lon]).setContent(div).openOn(map.m);
    });
  });
  ent.forEach((e, j) => L.marker([e.lat, e.lon], { icon: iconeEntrepot(e.id, couleur(j), S.ind.ouverts[j]), zIndexOffset: 1000 })
    .bindTooltip(`<b>${esc(e.id)} ${esc(e.nom)}</b><br>${nf(ch[j])} / ${nf(e.capacite)} palettes`).addTo(map.couche));
  $('#a-leg', el).innerHTML = ent.map((e, j) => `<span><span class="sw" style="background:var(--e${(j % 10) + 1})"></span>${esc(e.id)}</span>`).join('')
    + '<span><span class="sw" style="border-style:dashed;background:transparent;border-radius:50%"></span>Déplacé à la main</span>';
}
function dessinerConvergence() {
  const svg = $('#a-conv', el);
  if (!svg || !S.comp) return;
  svg.innerHTML = '';
  const W = 520, H = 220, m = { l: 62, r: 12, t: 12, b: 30 };
  svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
  const series = Object.entries(S.jobs).filter(([, j]) => j.resultat?.trace?.length).map(([k, j]) => [k, j.resultat.trace]);
  if (!series.length) return;
  const pts = series.flatMap(([, t]) => t);
  const tMax = Math.max(...pts.map((p) => p[0]), 0.01);
  const [y0, y1] = etendre(Math.min(...pts.map((p) => p[1])), Math.max(...pts.map((p) => p[1])), 0.05);
  const X = (v) => m.l + (v / tMax) * (W - m.l - m.r), Y = (v) => H - m.b - (v - y0) / (y1 - y0) * (H - m.t - m.b);
  const gx = graduations(0, tMax, 5), gy = graduations(y0, y1, 4);
  gx.valeurs.forEach((v) => { sv('line', { x1: X(v), y1: m.t, x2: X(v), y2: H - m.b, style: 'stroke:var(--trait);stroke-width:.6' }, svg); sv('text', { x: X(v), y: H - m.b + 13, 'text-anchor': 'middle' }, svg).textContent = nf(v, gx.pas < 1 ? (gx.pas < 0.1 ? 2 : 1) : 0); });
  gy.valeurs.forEach((v) => { sv('line', { x1: m.l, y1: Y(v), x2: W - m.r, y2: Y(v), style: 'stroke:var(--trait);stroke-width:.6' }, svg); sv('text', { x: m.l - 5, y: Y(v) + 3, 'text-anchor': 'end' }, svg).textContent = nf(v, gy.pas < 1 ? 2 : 0); });
  sv('line', { x1: m.l, y1: H - m.b, x2: W - m.r, y2: H - m.b, style: 'stroke:var(--encre);stroke-width:1.5' }, svg);
  sv('text', { x: W - m.r, y: H - 4, 'text-anchor': 'end' }, svg).textContent = 'temps (s)';
  const ordre = Object.keys(S.methodes);
  series.forEach(([k, t]) => {
    const c = `var(--e${(ordre.indexOf(k) % 10) + 1})`;
    let d = `M${X(t[0][0])} ${Y(t[0][1])}`;
    for (let i = 1; i < t.length; i++) d += ` H${X(t[i][0])} V${Y(t[i][1])}`;
    sv('path', { d, style: `fill:none;stroke:${c};stroke-width:${k === S.choix ? 3 : 1.8}` }, svg);
    const last = t[t.length - 1];
    sv('rect', { x: X(last[0]) - 3.5, y: Y(last[1]) - 3.5, width: 7, height: 7, style: `fill:${c};stroke:var(--encre);stroke-width:1` }, svg);
  });
  $('#a-conv-leg', el).innerHTML = series.map(([k]) => `<span><span class="sw" style="background:var(--e${(ordre.indexOf(k) % 10) + 1})"></span>${esc(S.methodes[k].num)} ${esc(S.methodes[k].nom)}</span>`).join('');
}

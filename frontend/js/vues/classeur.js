// Station 03 · Classeur d'échange : aperçu du .xlsx, téléchargement, import d'un classeur modifié, chargement au module 2.
import { S, $, $$, api, changer, nf, pct, esc, essayer, toast, plural } from '../core.js';
import { ouvrirScenario } from './tournees.js';

let el, ctx, feuille = 'Affectation', diff = null, liste = [];
const COLS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ';

export function init(racine, c) {
  el = racine; ctx = c;
  el.innerHTML = `
  <div class="vhead"><div class="t"><span class="lab">Station 03 · Lien entre les modules</span><h2>Classeur d'échange</h2>
    <p>La sortie du module 1 est un classeur Excel. Ouvrez-le, filtrez-le, changez la colonne « entrepot » si besoin : les charges et les coûts se recalculent dans Excel. Puis rechargez-le ici.</p></div>
    <label class="field" for="c-liste" style="min-width:280px">Scénario<select id="c-liste"></select></label></div>
  <div class="empty" id="c-vide"><span class="lab">Pas encore de classeur</span><div class="q">Validez une affectation</div>
    <p>Le classeur est créé quand vous validez une affectation au tableau de bord 1. Vous pouvez aussi importer un classeur existant.</p>
    <div class="row"><button class="btn" type="button" id="c-vers-m1">Aller au tableau de bord 1</button><label class="btn" for="c-fichier">Importer un classeur</label></div></div>
  <div class="stack" id="c-plein" style="gap:20px" hidden>
    <div class="xl">
      <div class="xl-bar"><span class="mono" style="font-size:11.5px;font-weight:600" id="c-nom"></span><span class="ref" id="c-ref">A1</span>
        <span class="mono" style="font-size:11px;color:var(--gris-2)">fx</span><span class="val" id="c-val"></span>
        <a class="btn sm" id="c-dl" href="#" download>Télécharger .xlsx</a></div>
      <div class="xl-grid"><table id="c-table"></table></div>
      <div class="xl-tabs" role="tablist" id="c-tabs"></div>
    </div>
    <div class="g2">
      <div class="stack">
        <label class="drop" id="c-drop" for="c-fichier"><b>Importer le classeur modifié</b>
          <span class="hint">Glissez le .xlsx ici ou cliquez. Les magasins déplacés sont détectés, les capacités contrôlées.</span></label>
        <div class="pan" id="c-diff" hidden><div class="pan-h"><h3>Résultat de l'import</h3><span class="code">IMPORT</span></div><div class="pan-b diff" id="c-diff-b"></div></div>
      </div>
      <div class="pan"><div class="pan-h"><h3>Résumé du scénario</h3><span class="code">SCÉNARIO</span></div><div class="pan-b flush"><div class="scroll"><table class="tbl kv" id="c-resume"></table></div></div></div>
    </div>
    <div class="decide"><span class="lab">Transmission</span><div class="q" id="c-q">Charger ce classeur dans le module 2 ?</div><p id="c-p"></p>
      <div class="row"><button class="go" type="button" id="c-go">Charger dans le module 2</button></div></div>
  </div>
  <input type="file" id="c-fichier" accept=".xlsx,.json,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/json" hidden>`;
  const fic = $('#c-fichier', el), drop = $('#c-drop', el);
  fic.addEventListener('change', () => { if (fic.files[0]) importer(fic.files[0]); fic.value = ''; });
  drop.addEventListener('dragover', (e) => { e.preventDefault(); drop.classList.add('over'); });
  drop.addEventListener('dragleave', () => drop.classList.remove('over'));
  drop.addEventListener('drop', (e) => { e.preventDefault(); drop.classList.remove('over'); if (e.dataTransfer.files[0]) importer(e.dataTransfer.files[0]); });
  $('#c-vers-m1', el).addEventListener('click', () => ctx.aller('affectation'));
  $('#c-liste', el).addEventListener('change', async (e) => { if (e.target.value) { S.scenario = e.target.value; diff = null; await rafraichir(); changer(); } });
  $('#c-table', el).addEventListener('click', (e) => { const td = e.target.closest('td'); if (td) cellule(td); });
  $('#c-go', el).addEventListener('click', async () => {
    const ok = await ouvrirScenario(S.scenario);
    if (ok) { toast(`Module 2 : scénario ${S.scenario} chargé.`, 'ok'); ctx.aller('tournees'); }
  });
}

export async function entrer() {
  const r = await api('/api/m2/scenarios').catch(() => null);
  if (r) liste = r.scenarios;
  rendre();
}

export async function rafraichir({ silencieux = false } = {}) {
  if (!S.scenario) { S.feuilles = null; rendre(); return; }
  const r = await (silencieux ? api(`/api/m2/scenario/${encodeURIComponent(S.scenario)}/feuilles`).catch(() => null)
    : essayer(() => api(`/api/m2/scenario/${encodeURIComponent(S.scenario)}/feuilles`), 'Classeur indisponible.'));
  S.feuilles = r || null;
  if (r && !liste.some((x) => x.scenario === S.scenario)) { const l = await api('/api/m2/scenarios').catch(() => null); if (l) liste = l.scenarios; }
  rendre();
}

async function importer(f) {
  const fd = new FormData(); fd.append('fichier', f);
  const r = await essayer(() => api('/api/m2/scenario', { form: fd }), 'Import refusé.');
  if (!r) return;
  diff = r.import_;
  S.scenario = r.scenario;
  await rafraichir();
  if (diff.deplaces.length) toast(`${plural(diff.deplaces.length, 'magasin déplacé', 'magasins déplacés')} : nouveau scénario ${r.scenario}.`, 'ok', 7000);
  else toast(diff.origine ? 'Classeur identique au scénario d’origine.' : `Scénario ${r.scenario} importé.`, 'info');
  changer();
}

function fmt(v, col) {
  if (v == null || v === '') return '';
  if (typeof v !== 'number') return esc(v);
  if (col === 'taux_utilisation') return pct(v, 1);
  if (col === 'latitude' || col === 'longitude' || col === 'kpal') return nf(v, 4);
  return Number.isInteger(v) ? nf(v) : nf(v, 2);
}
function rendre() {
  if (!el) return;
  $('#c-liste', el).innerHTML = (liste.length ? '' : '<option value="">Aucun scénario</option>')
    + liste.map((s) => `<option value="${esc(s.scenario)}" ${s.scenario === S.scenario ? 'selected' : ''}>${esc(s.scenario)}${s.ajustements ? ` · ${s.ajustements} modif.` : ''}</option>`).join('');
  const f = S.feuilles;
  $('#c-vide', el).hidden = !!f; $('#c-plein', el).hidden = !f;
  if (!f) return;
  $('#c-nom', el).textContent = f.fichier;
  $('#c-dl', el).href = `/api/m2/scenario/${encodeURIComponent(S.scenario)}/xlsx`;
  $('#c-dl', el).setAttribute('download', f.fichier);
  const noms = Object.keys(f.feuilles);
  if (!noms.includes(feuille)) feuille = noms[1] || noms[0];
  $('#c-tabs', el).innerHTML = noms.map((n) => `<button type="button" role="tab" id="ct-${esc(n.normalize('NFD').replace(/[^\w]/g, ''))}" aria-selected="${n === feuille}" data-f="${esc(n)}">${esc(n)}</button>`).join('');
  $$('#c-tabs button', el).forEach((b) => b.onclick = () => { feuille = b.dataset.f; rendre(); });
  const rows = f.feuilles[feuille], nc = Math.max(...rows.map((r) => r.length));
  const tete = feuille === 'Lisez-moi' ? null : rows[0];
  let h = `<thead><tr><th></th>${[...Array(nc)].map((_, c) => `<th>${COLS[c] || c}</th>`).join('')}</tr></thead><tbody>`;
  rows.forEach((r, ri) => {
    h += `<tr><th>${ri + 1}</th>`;
    for (let c = 0; c < nc; c++) {
      const v = r[c], col = tete ? tete[c] : null, entete = tete && ri === 0;
      const cls = [entete ? 'h' : '', typeof v === 'number' ? 'n' : '', col === 'entrepot' ? 'edit' : '',
        col === 'taux_utilisation' && v > 1 ? 'over' : ''].join(' ');
      h += `<td class="${cls}" data-ref="${COLS[c]}${ri + 1}" data-v="${esc(v ?? '')}">${entete ? esc(v) : fmt(v, col)}</td>`;
    }
    h += '</tr>';
  });
  $('#c-table', el).innerHTML = h + '</tbody>';
  const premier = $('#c-table td', el); if (premier) cellule(premier);
  // résumé
  const scn = Object.fromEntries(f.feuilles['Scénario'].slice(1));
  const ent = f.feuilles['Entrepôts'].slice(1);
  $('#c-resume', el).innerHTML = `<tbody>
    <tr><td>Scénario</td><td class="r">${esc(scn.scenario)}</td></tr>
    <tr><td>Origine</td><td class="r">${esc(scn.parent || 'module 1')}</td></tr>
    <tr><td>Instance · modèle</td><td class="r">${esc(scn.instance)} · ${esc(String(scn.modele).toUpperCase())}</td></tr>
    <tr><td>Méthode</td><td class="r">${esc(S.methodes[scn.methode] ? S.methodes[scn.methode].num + ' ' + S.methodes[scn.methode].nom : scn.methode)}</td></tr>
    <tr><td>Magasins</td><td class="r">${nf(f.feuilles['Affectation'].length - 1)}</td></tr>
    <tr><td>Entrepôts servant au moins un magasin</td><td class="r">${ent.filter((e) => e[5] > 0).length} / ${ent.length}</td></tr>
    <tr class="tot"><td>Coût d'affectation total</td><td class="r">${nf(scn.cout_total, 2)} ${esc(scn.unite_cout || '')}</td></tr></tbody>`;
  // différences
  $('#c-diff', el).hidden = !diff;
  if (diff) {
    $('#c-diff-b', el).innerHTML = diff.deplaces.length
      ? `<span class="st s-tendu">${plural(diff.deplaces.length, 'magasin déplacé', 'magasins déplacés')}</span>
         <span>${diff.deplaces.map((d) => `<b>${esc(d.magasin)}</b> ${esc(d.de)} → ${esc(d.vers)}`).join(' · ')}</span>
         <span>Nouveau scénario dérivé de <span class="mono">${esc(diff.origine)}</span>. Au module 2, seuls <b>${diff.entrepots_touches.map(esc).join(', ')}</b> seront recalculés.</span>`
      : `<span class="st s-ok">Aucun changement</span><span>${diff.origine ? 'Le classeur correspond au scénario d’origine.' : 'Scénario importé tel quel.'}</span>`;
  }
  const charge = S.m2.sc?.scenario === S.scenario;
  $('#c-q', el).textContent = charge ? 'Classeur chargé au module 2' : 'Charger ce classeur dans le module 2 ?';
  $('#c-p', el).textContent = charge ? 'Le module 2 travaille déjà sur ce scénario.'
    : 'Le module 2 lit uniquement cette affectation, forme un groupe de magasins par entrepôt et calcule les matrices de distances et de temps.';
  $('#c-go', el).textContent = charge ? 'Ouvrir le module 2' : 'Charger dans le module 2';
}
function cellule(td) {
  $$('#c-table td.on', el).forEach((x) => x.classList.remove('on'));
  td.classList.add('on');
  $('#c-ref', el).textContent = td.dataset.ref; $('#c-val', el).textContent = td.dataset.v;
}

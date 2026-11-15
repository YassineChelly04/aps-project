// Station 05 · Plan de distribution final : indicateurs consolidés (module 1 + module 2), carte du réseau, export.
import { S, $, api, changer, nf, pct, hm, esc, essayer, carte, couleur, iconeEntrepot, css, plural } from '../core.js';
import { iconeMethode } from './tournees.js';

let el, ctx, map;

export function init(racine, c) {
  el = racine; ctx = c;
  el.innerHTML = `
  <div class="vhead"><div class="t"><span class="lab">Station 05 · Plan de distribution final</span><h2>Le réseau retenu</h2>
    <p>Affectations du module 1 et tournées du module 2 dans une même vue. Les distances et temps sont recalculés par le serveur à partir des séquences choisies.</p></div>
    <label class="field" for="p-liste" style="min-width:280px">Plan enregistré<select id="p-liste"></select></label></div>
  <div class="empty" id="p-vide"><span class="lab">Aucun plan</span><div class="q">Validez des tournées</div>
    <p>Choisissez un compromis par entrepôt au tableau de bord 2, puis « Valider le plan ».</p>
    <div class="row"><button class="btn" type="button" id="p-vers-t">Aller aux tournées</button></div></div>
  <div class="stack" id="p-plein" style="gap:20px" hidden>
    <div class="kpis" id="p-kpis"></div>
    <div class="g-wide">
      <div class="pan"><div class="pan-h"><h3>Carte du réseau</h3><span class="code" id="p-code"></span></div>
        <div class="pan-b"><div class="carte h-l" id="p-carte"></div><div class="leg" id="p-leg"></div></div></div>
      <div class="stack" style="gap:20px">
        <div class="pan"><div class="pan-h"><h3>Exports</h3><span class="code">PLAN-EXPORT</span></div><div class="pan-b">
          <p class="hint">Excel : synthèse, une ligne par arrêt (rang, distance et temps cumulés) et paramètres. CSV : les arrêts, séparateur point-virgule.</p>
          <div class="row"><a class="btn" id="p-xlsx" href="#">Exporter le plan .xlsx</a><a class="btn" id="p-csv" href="#">Exporter les arrêts .csv</a></div></div></div>
        <div class="pan"><div class="pan-h"><h3>Paramètres des tournées</h3><span class="code">PLAN-PARAM</span></div><div class="pan-b flush"><table class="tbl kv" id="p-param"></table></div></div>
      </div>
    </div>
    <div class="pan"><div class="pan-h"><h3>Tournées par entrepôt</h3><span class="code">PLAN-TABLE</span></div>
      <div class="pan-b flush"><div class="scroll"><table class="tbl" id="p-table"></table></div></div></div>
    <div class="decide"><span class="lab">Décision</span><div class="q">Comparer avec d'autres scénarios ?</div>
      <p>Le plan est enregistré. Comparez-le aux scénarios précédents, ou repartez d'une autre affectation.</p>
      <div class="row"><button class="btn" type="button" id="p-autre">Modifier l'affectation</button><button class="go" type="button" id="p-go">Comparer les scénarios</button></div></div>
  </div>`;
  map = carte($('#p-carte', el));
  $('#p-vers-t', el).onclick = () => ctx.aller('tournees');
  $('#p-go', el).onclick = () => ctx.aller('scenarios');
  $('#p-autre', el).onclick = () => ctx.aller('affectation');
  $('#p-liste', el).addEventListener('change', async (e) => { if (e.target.value) await ouvrirPlan(e.target.value); });
}

export async function ouvrirPlan(sc) {
  const p = await essayer(() => api(`/api/m2/plan/${encodeURIComponent(sc)}`), 'Plan introuvable.');
  if (p) { S.plan = p; changer(); rendre(); }
  return !!p;
}
export function entrer() { rendre(); map.m.invalidateSize(); }
export function recolorer() { rendre(); }

function rendre() {
  if (!el) return;
  $('#p-liste', el).innerHTML = (S.plans.length ? '' : '<option value="">Aucun plan</option>')
    + [...S.plans].reverse().map((p) => `<option value="${esc(p.scenario)}" ${p.scenario === S.plan?.scenario ? 'selected' : ''}>${esc(p.scenario)}</option>`).join('');
  const p = S.plan;
  $('#p-vide', el).hidden = !!p; $('#p-plein', el).hidden = !p;
  if (!p) return;
  const t = p.totaux;
  $('#p-kpis', el).innerHTML = `
    <div><small>Coût d'affectation</small><b>${nf(p.cout_m1)}</b><span class="sub">TND / semaine · module 1</span></div>
    <div><small>Distance des tournées</small><b>${nf(t.distance_km, 1)} km</b><span class="sub">${plural(p.n_tournees, 'tournée')}</span></div>
    <div><small>Temps total</small><b>${hm(t.temps_total_min)}</b><span class="sub">dont service ${hm(t.service_min)}</span></div>
    <div><small>Arrêts</small><b>${nf(t.arrets)}</b><span class="sub">${nf(t.demande)} palettes / semaine</span></div>
    <div><small>Coût des tournées</small><b>${nf(t.cout_tournees)}</b><span class="sub">TND / semaine (estimé)</span></div>`;
  $('#p-code', el).textContent = p.scenario;
  $('#p-xlsx', el).href = `/api/m2/plan/${encodeURIComponent(p.scenario)}/export?format=xlsx`;
  $('#p-csv', el).href = `/api/m2/plan/${encodeURIComponent(p.scenario)}/export?format=csv`;
  const pa = p.parametres;
  $('#p-param', el).innerHTML = `<tbody>
    <tr><td>Facteur route / vol d'oiseau</td><td class="r">${nf(pa.facteur_route, 2)}</td></tr>
    <tr><td>Vitesses</td><td class="r">${pa.vitesses.map((v) => `${v.troncon_jusqu_a_km == null ? 'au-delà' : '≤ ' + nf(v.troncon_jusqu_a_km) + ' km'} : ${nf(v.kmh)} km/h`).join(' · ')}</td></tr>
    <tr><td>Congestion par tronçon</td><td class="r">× ${nf(pa.congestion[0], 1)} à ${nf(pa.congestion[1], 1)}</td></tr>
    <tr><td>Service par arrêt</td><td class="r">${nf(pa.service_min)} min</td></tr>
    <tr><td>Véhicule</td><td class="r">${nf(pa.capacite_vehicule)} palettes · ${nf(pa.cout_km, 2)} TND/km</td></tr></tbody>`;
  $('#p-table', el).innerHTML = `<thead><tr><th>Entrepôt</th><th>Méthode</th><th class="r">Arrêts</th><th class="r">Demande</th><th class="r">Distance</th>
    <th class="r">Conduite</th><th class="r">Service</th><th class="r">Temps total</th><th class="r">Rotations</th><th class="r">Coût tournées</th></tr></thead><tbody>
    ${p.tournees.map((l, j) => `<tr><td><span class="sw" style="background:${couleur(idx(p, l.entrepot))}"></span><b>${esc(l.entrepot)}</b> ${esc(String(l.nom).split(' (')[0])}</td>
      <td>${iconeMethode(l.methode)} ${esc(S.m2.methodes[l.methode]?.nom || l.methode)}</td><td class="r">${l.arrets}</td><td class="r">${nf(l.demande)}</td>
      <td class="r">${nf(l.distance_km, 1)} km</td><td class="r">${hm(l.conduite_min)}</td><td class="r">${hm(l.service_min)}</td><td class="r">${hm(l.temps_total_min)}</td>
      <td class="r">${l.rotations}</td><td class="r">${nf(l.cout_tournees)}</td></tr>`).join('')}
    <tr class="tot"><td>Réseau</td><td></td><td class="r">${t.arrets}</td><td class="r">${nf(t.demande)}</td><td class="r">${nf(t.distance_km, 1)} km</td>
      <td class="r">${hm(t.conduite_min)}</td><td class="r">${hm(t.service_min)}</td><td class="r">${hm(t.temps_total_min)}</td><td></td><td class="r">${nf(t.cout_tournees)}</td></tr></tbody>`;
  // carte : une couleur par entrepôt
  map.vider();
  const pts = [];
  p.tournees.forEach((l) => {
    const arr = p.arrets.filter((a) => a.entrepot === l.entrepot).sort((a, b) => a.rang - b.rang);
    if (!arr.length) return;
    const dep = arr[arr.length - 1], c = couleur(idx(p, l.entrepot));
    const ligne = [[dep.lat, dep.lon], ...arr.map((a) => [a.lat, a.lon])];
    pts.push(...ligne);
    L.polyline(ligne, { color: css('--encre'), weight: 5, opacity: 0.85, interactive: false }).addTo(map.couche);
    L.polyline(ligne, { color: c, weight: 3, opacity: 1 }).bindTooltip(`<b>${esc(l.entrepot)}</b> · ${nf(l.distance_km, 1)} km · ${hm(l.temps_total_min)}`).addTo(map.couche);
    arr.slice(0, -1).forEach((a) => L.circleMarker([a.lat, a.lon], { radius: 4.5, color: css('--carte'), weight: 1.5, fillColor: c, fillOpacity: 1 })
      .bindTooltip(`${a.rang}. ${esc(a.arret)} · ${nf(a.demande)} pal.`).addTo(map.couche));
    L.marker([dep.lat, dep.lon], { icon: iconeEntrepot(l.entrepot, c), zIndexOffset: 1000 }).addTo(map.couche);
  });
  map.cadrer(pts);
  $('#p-leg', el).innerHTML = p.tournees.map((l) => `<span><span class="sw" style="background:${couleur(idx(p, l.entrepot))}"></span>${esc(l.entrepot)} · ${l.arrets} arrêts</span>`).join('');
}
function idx(p, id) {
  const liste = S.m2.sc?.scenario === p.scenario ? S.m2.sc.entrepots.map((e) => e.id) : S.inst?.entrepots.map((e) => e.id) || [];
  const k = liste.indexOf(id);
  return k >= 0 ? k : p.tournees.findIndex((l) => l.entrepot === id);
}

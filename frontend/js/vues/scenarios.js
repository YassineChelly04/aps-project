// Station 06 · Comparaison des scénarios enregistrés, et retour vers le module 1 (coûts corrigés par les tournées).
import { S, $, $$, api, changer, nf, pct, hm, esc, essayer, toast } from '../core.js';
import { ouvrirPlan } from './plan.js';
import { chargerParId } from './donnees.js';

let el, ctx, ref = null;

export function init(racine, c) {
  el = racine; ctx = c;
  el.innerHTML = `
  <div class="vhead"><div class="t"><span class="lab">Station 06 · Décision</span><h2>Comparer les scénarios</h2>
    <p>Chaque plan enregistré garde son coût d'affectation (module 1) et les totaux de ses tournées (module 2). Choisissez la référence : les écarts sont calculés par rapport à elle.</p></div></div>
  <div class="empty" id="s-vide"><span class="lab">Aucun plan enregistré</span><div class="q">Enregistrez un premier plan</div>
    <p>Un plan est enregistré quand vous validez les tournées au tableau de bord 2.</p></div>
  <div class="stack" id="s-plein" style="gap:20px" hidden>
    <div class="pan"><div class="pan-h"><h3>Scénarios enregistrés</h3><span class="code">SCN-TABLE</span></div>
      <div class="pan-b flush"><div class="scroll"><table class="tbl" id="s-table"></table></div></div></div>
    <div class="g3" id="s-barres"></div>
    <div class="pan"><div class="pan-h"><h3>Retour vers le module 1</h3><span class="code">SCN-RETOUR · FACULTATIF</span></div><div class="pan-b">
      <p class="muted" id="s-fb-txt" style="font-size:14px"></p>
      <div class="scroll"><table class="tbl" id="s-fb"></table></div>
      <div class="row"><button class="btn" type="button" id="s-retour">Relancer le module 1 avec ces coûts</button></div></div></div>
    <div class="decide"><span class="lab">Nouveau scénario</span><div class="q">Essayer une autre affectation ?</div>
      <p>Retour au tableau de bord 1. Au module 2, seuls les entrepôts dont les magasins changent seront recalculés.</p>
      <div class="row"><button class="go" type="button" id="s-go">Modifier l'affectation</button></div></div>
  </div>`;
  $('#s-go', el).onclick = () => ctx.aller('affectation');
  $('#s-retour', el).onclick = retour;
  $('#s-table', el).addEventListener('click', async (e) => {
    const r = e.target.closest('[data-ref]'); if (r) { ref = r.dataset.ref; rendre(); return; }
    const o = e.target.closest('[data-ouvrir]'); if (o && await ouvrirPlan(o.dataset.ouvrir)) ctx.aller('plan');
  });
}

export async function entrer() {
  const l = await api('/api/m2/plans').catch(() => null);
  if (l) { S.plans = l.plans; changer(); }
  rendre();
}
export function recolorer() { rendre(); }

const delta = (a, b) => { if (a == null || b == null || !b) return '—'; const v = (a / b - 1) * 100; return `${v > 0 ? '+' : ''}${nf(v, 1)} %`; };
function rendre() {
  if (!el) return;
  const pl = S.plans;
  $('#s-vide', el).hidden = !!pl.length; $('#s-plein', el).hidden = !pl.length;
  if (!pl.length) return;
  if (!pl.some((p) => p.scenario === ref)) ref = pl[0].scenario;
  const r = pl.find((p) => p.scenario === ref);
  $('#s-table', el).innerHTML = `<thead><tr><th>Réf.</th><th>Scénario</th><th>Méthode M1</th><th class="r">Modifs</th><th class="r">Coût M1</th><th class="r">Δ</th>
    <th class="r">Distance</th><th class="r">Δ</th><th class="r">Temps total</th><th class="r">Δ</th><th class="r">Coût tournées</th><th></th></tr></thead><tbody>
    ${pl.map((p) => `<tr class="${p.scenario === ref ? 'sel' : ''}">
      <td><input type="radio" name="s-ref" id="sr-${esc(p.scenario)}" data-ref="${esc(p.scenario)}" ${p.scenario === ref ? 'checked' : ''} aria-label="Référence ${esc(p.scenario)}"></td>
      <td><b class="mono" style="font-size:11.5px">${esc(p.scenario)}</b><small>${esc(p.instance)} · ${esc(String(p.modele).toUpperCase())} · ${esc(p.date.replace('T', ' '))}</small></td>
      <td>${esc(S.methodes[p.methode_m1] ? S.methodes[p.methode_m1].num + ' ' + S.methodes[p.methode_m1].nom : p.methode_m1)}</td>
      <td class="r">${p.ajustements}</td><td class="r">${nf(p.cout_m1)}</td><td class="r">${p.scenario === ref ? '' : delta(p.cout_m1, r.cout_m1)}</td>
      <td class="r">${nf(p.distance_km, 1)} km</td><td class="r">${p.scenario === ref ? '' : delta(p.distance_km, r.distance_km)}</td>
      <td class="r">${hm(p.temps_total_min)}</td><td class="r">${p.scenario === ref ? '' : delta(p.temps_total_min, r.temps_total_min)}</td>
      <td class="r">${nf(p.cout_tournees)}</td><td><button class="btn sm" type="button" data-ouvrir="${esc(p.scenario)}">Ouvrir</button></td></tr>`).join('')}</tbody>`;
  // trois comparaisons en barres
  const metr = [['cout_m1', 'Coût d’affectation', (v) => nf(v) + ' TND'], ['distance_km', 'Distance des tournées', (v) => nf(v, 1) + ' km'], ['temps_total_min', 'Temps des tournées', hm]];
  $('#s-barres', el).innerHTML = metr.map(([k, lib, f]) => {
    const max = Math.max(...pl.map((p) => p[k] || 0)) || 1;
    return `<div class="pan"><div class="pan-h"><h3>${lib}</h3></div><div class="pan-b"><div class="gauges">${pl.map((p) => `
      <div class="gauge" style="grid-template-columns:minmax(70px,110px) minmax(0,1fr) auto"><span class="mono" style="font-size:10.5px" title="${esc(p.scenario)}">${esc(court(p.scenario))}</span>
      <div class="b"><i style="width:${(p[k] || 0) / max * 100}%;background:${p.scenario === ref ? 'var(--encre)' : 'var(--bleu)'}"></i></div><span class="mono" style="font-size:11px">${f(p[k])}</span></div>`).join('')}</div></div></div>`;
  }).join('');
  // retour
  const p = S.plan;
  if (!p) { $('#s-fb-txt', el).textContent = 'Ouvrez un plan pour comparer le coût de ses tournées au coût de transport supposé dans c_ij.'; $('#s-fb', el).innerHTML = ''; $('#s-retour', el).disabled = true; return; }
  $('#s-retour', el).disabled = false;
  const tm1 = p.totaux.transport_m1, ct = p.totaux.cout_tournees;
  $('#s-fb-txt', el).innerHTML = `Plan <span class="mono">${esc(p.scenario)}</span>. Le module 1 suppose un aller-retour par magasin et par palette ; les tournées regroupent les livraisons. `
    + (tm1 ? `Transport supposé : <b>${nf(tm1)} TND</b>, coût estimé des tournées : <b>${nf(ct)} TND</b> (rapport ${nf(ct / tm1, 2)}). Relancer le module 1 applique ce rapport, entrepôt par entrepôt, à la part transport de c<sub>ij</sub>.` : '');
  $('#s-fb', el).innerHTML = `<thead><tr><th>Entrepôt</th><th class="r">Transport supposé (M1)</th><th class="r">Coût des tournées</th><th class="r">Rapport</th></tr></thead><tbody>
    ${p.tournees.map((l) => `<tr><td>${esc(l.entrepot)} ${esc(String(l.nom).split(' (')[0])}</td><td class="r">${nf(l.transport_m1)}</td><td class="r">${nf(l.cout_tournees)}</td>
      <td class="r"><span class="st ${l.ratio_retour == null ? 's-gris' : Math.abs(l.ratio_retour - 1) > 0.25 ? 's-tendu' : 's-ok'}">× ${nf(l.ratio_retour, 2)}</span></td></tr>`).join('')}</tbody>`;
}
// Fin distinctive de l'identifiant (horodatage + révision), ex. « 230445~x1 ».
const court = (s) => s.split('-').slice(-1)[0];

async function retour() {
  if (!S.plan) return;
  const r = await essayer(() => api('/api/m2/retour', { json: { scenario: S.plan.scenario } }), 'Retour impossible.');
  if (!r) return;
  await chargerParId(r.instance, { silencieux: true });
  toast(`Instance ${r.instance} créée avec les coûts corrigés. Relancez les méthodes du module 1.`, 'ok', 8000);
  ctx.aller('affectation');
}

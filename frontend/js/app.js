// Sijar · navigation, statuts des étapes, « prochaine action », thème et reprise de session.
import { S, $, api, changer, surChangement, relire, champ, recolorerChamps, essayer, toast } from './core.js';
import * as donnees from './vues/donnees.js';
import * as affectation from './vues/affectation.js';
import * as classeur from './vues/classeur.js';
import * as tournees from './vues/tournees.js';
import * as plan from './vues/plan.js';
import * as scenarios from './vues/scenarios.js';

const VUES = [
  { id: 'donnees', n: '01', t: 'Données', zone: '', zt: 'DATA', groupe: 'Module 1 · Distribution', mod: donnees },
  { id: 'affectation', n: '02', t: 'Affectation', zone: 'z1', zt: 'M1', mod: affectation },
  { id: 'classeur', n: '03', t: 'Classeur', zone: 'z1', zt: 'M1 → M2', mod: classeur },
  { id: 'tournees', n: '04', t: 'Tournées', zone: 'z2', zt: 'M2', groupe: 'Module 2 · Tournées', mod: tournees },
  { id: 'plan', n: '05', t: 'Plan final', zone: 'z2', zt: 'PLAN', mod: plan },
  { id: 'scenarios', n: '06', t: 'Scénarios', zone: '', zt: 'SCN', groupe: 'Décision', mod: scenarios },
];
let courante = 'donnees';

const enCalcul1 = () => Object.values(S.jobs).some((j) => j.etat === 'en_attente' || j.etat === 'en_cours');
function statut(id) {
  switch (id) {
    case 'donnees': return S.inst ? [`${S.inst.n} magasins · ${S.inst.m} entrepôts`, 'ok'] : ['À charger', 'todo'];
    case 'affectation':
      if (!S.inst) return ['En attente', ''];
      if (enCalcul1()) return ['Calcul en cours', 'todo'];
      if (!S.comp) return ['À lancer', 'todo'];
      return S.valide ? ['Validée', 'ok'] : ['À valider', 'todo'];
    case 'classeur':
      if (!S.scenario) return ['En attente', ''];
      return S.m2.sc?.scenario === S.scenario ? ['Chargé au module 2', 'ok'] : ['À charger', 'todo'];
    case 'tournees':
      if (!S.m2.sc) return ['En attente', ''];
      if (S.m2.job) return ['Calcul en cours', 'todo'];
      if (!S.m2.res) return ['À calculer', 'todo'];
      return S.plan?.scenario === S.m2.sc.scenario ? ['Plan validé', 'ok'] : ['À valider', 'todo'];
    case 'plan': return S.plan ? ['Enregistré', 'ok'] : ['En attente', ''];
    case 'scenarios': return [`${S.plans.length} plan${S.plans.length > 1 ? 's' : ''} enregistré${S.plans.length > 1 ? 's' : ''}`, ''];
  }
  return ['', ''];
}
const ACTIONS = {
  donnees: 'Charger une instance', affectation: 'Lancer puis valider', classeur: 'Charger dans le module 2',
  tournees: 'Calculer puis valider', plan: 'Enregistrer le plan',
};
function prochaine() {
  for (const v of VUES) {
    const [, k] = statut(v.id);
    if (k === 'todo') return [v.id, ACTIONS[v.id] || v.t];
  }
  return S.plans.length ? ['scenarios', 'Comparer les scénarios'] : null;
}

function rendreNav() {
  const ul = $('#nav');
  ul.innerHTML = '';
  VUES.forEach((v) => {
    if (v.groupe) { const li = document.createElement('li'); li.className = 'sep'; li.textContent = v.groupe; ul.appendChild(li); }
    const [s, k] = statut(v.id);
    const li = document.createElement('li');
    li.innerHTML = `<button type="button" id="nav-${v.id}" ${v.id === courante ? 'aria-current="page"' : ''}>
      <span class="n">${v.n}</span><span class="t">${v.t}</span><span class="s ${k === 'todo' ? 'todo' : ''}">${s}</span></button>`;
    li.firstElementChild.addEventListener('click', () => aller(v.id));
    ul.appendChild(li);
  });
  const p = prochaine();
  const b = $('#suivant');
  b.hidden = !p || p[0] === courante;
  if (p) { $('#suivant-txt').textContent = p[1]; b.dataset.vue = p[0]; }
  $('#pied-inst').textContent = S.inst?.id || '—';
  $('#pied-scn').textContent = S.m2.sc?.scenario || S.scenario || '—';
}

export function aller(id, { defiler = true } = {}) {
  const v = VUES.find((x) => x.id === id) || VUES[0];
  courante = v.id;
  document.querySelectorAll('.view').forEach((s) => { s.hidden = s.dataset.vue !== v.id; });
  $('#titre').textContent = v.t;
  const z = $('#zone'); z.className = 'zone ' + v.zone; z.textContent = v.zt;
  if (location.hash !== '#' + v.id) history.replaceState(null, '', '#' + v.id);
  rendreNav();
  v.mod.entrer?.();
  if (defiler) window.scrollTo({ top: 0, behavior: 'auto' });
}
window.sijarAller = aller;

$('#suivant').addEventListener('click', (e) => aller(e.currentTarget.dataset.vue));
$('#theme').addEventListener('click', () => {
  const sombre = document.documentElement.dataset.theme !== 'dark';
  if (sombre) document.documentElement.dataset.theme = 'dark'; else delete document.documentElement.dataset.theme;
  try { localStorage.setItem('sijar.theme', sombre ? 'dark' : 'light'); } catch (e) { /* rien */ }
  recolorerChamps();
  VUES.forEach((v) => v.mod.recolorer?.());
});
window.addEventListener('hashchange', () => aller(location.hash.slice(1), { defiler: false }));
surChangement(rendreNav);

// ---------------------------------------------------------------- démarrage
champ($('#fond'), { mode: 0, k: 22, a: 0.06, dpr: 1 });
VUES.forEach((v) => v.mod.init(document.getElementById('v-' + v.id), { aller }));

async function demarrer() {
  const ex = await essayer(() => api('/api/exemples'), 'Chargement impossible.');
  if (ex) { S.exemples = ex.exemples; S.methodes = ex.methodes; S.phases = ex.phases; }
  const m2 = await essayer(() => api('/api/m2/methodes'));
  if (m2) { S.m2.methodes = m2.methodes; S.m2.service = m2.service_min; }
  const pl = await essayer(() => api('/api/m2/plans'));
  if (pl) S.plans = pl.plans;
  const sauve = relire();
  if (sauve) Object.assign(S, { modele: sauve.modele || 'gap', limite: sauve.limite || 30, graine: sauve.graine || 0 });
  // Reprise : instance et scénario de la dernière session, sinon le petit jeu tunisien.
  const id = sauve?.inst || S.exemples[0]?.id;
  if (id) await donnees.chargerParId(id, { silencieux: true });
  if (sauve?.scenario) {
    S.scenario = sauve.scenario;
    await classeur.rafraichir({ silencieux: true });
    if (!S.feuilles) S.scenario = null;
  }
  if (sauve?.m2sc) await tournees.ouvrirScenario(sauve.m2sc, { silencieux: true });
  changer();
  aller(location.hash.slice(1) || 'donnees', { defiler: false });
  if (!S.inst) toast('Aucune instance trouvée. Lancez « python donnees_tunisie/generer_instances.py ».', 'warn', 9000);
}
demarrer();

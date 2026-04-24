import { FileText, Clock, CheckCircle, XCircle, AlertTriangle, CalendarDays, Zap, Star, Users, Award, Timer, Activity, AlignLeft } from 'lucide-react'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, Legend, LineChart, Line, CartesianGrid,
} from 'recharts'

// Infer status from exception field
function getStatut(f) {
  if (f.statut_validation) return f.statut_validation
  const exc = f.exception
  if (!exc || exc === '[]' || exc === 'None' || exc === 'null') return 'accepté'
  return 'accepté_avec_réserve'
}

function KPICard({ Icon, label, value, color, sub }) {
  return (
    <div className="card flex items-center gap-4 min-h-[88px]">
      <div className={`p-3 rounded-xl flex-shrink-0 ${color}`}>
        <Icon size={22} className="text-white" />
      </div>
      <div className="min-w-0">
        <p className="text-2xl font-bold text-gray-900 leading-tight">{value}</p>
        <p className="text-sm text-gray-500 leading-snug">{label}</p>
        {sub && <p className="text-xs text-gray-400 mt-0.5 leading-snug">{sub}</p>}
      </div>
    </div>
  )
}

export default function Dashboard({ factures, dbError }) {
  const now = new Date()
  const total = factures.length

  const statuts = factures.map(getStatut)
  const nbAccepte = statuts.filter(s => s === 'accepté').length
  const nbReserve = statuts.filter(s => s === 'accepté_avec_réserve').length
  const nbRejete  = statuts.filter(s => s === 'rejeté').length

  // Ce mois
  const cesMois = (f) => {
    if (!f.date_creation) return false
    const d = new Date(f.date_creation)
    return d.getMonth() === now.getMonth() && d.getFullYear() === now.getFullYear()
  }
  const acceptesMois = factures.filter(f => getStatut(f) === 'accepté' && cesMois(f)).length
  const rejetesMois  = factures.filter(f => getStatut(f) === 'rejeté'  && cesMois(f)).length

  // Montants
  const totalMAD = factures
    .filter(f => (f.devise === 'MAD' || !f.devise) && f.montant_ttc)
    .reduce((s, f) => s + f.montant_ttc, 0)
  // Pie chart
  const pieData = [
    { name: 'Validées',      value: nbAccepte, fill: '#22c55e' },
    { name: 'Avec réserve',  value: nbReserve, fill: '#f59e0b' },
    { name: 'Rejetées',      value: nbRejete,  fill: '#ef4444' },
  ].filter(d => d.value > 0)

  // Bar chart — 6 derniers mois
  const months = Array.from({ length: 6 }, (_, i) => {
    const d = new Date(now.getFullYear(), now.getMonth() - (5 - i), 1)
    return {
      period: d.toLocaleDateString('fr-FR', { month: 'short', year: '2-digit' }),
      year: d.getFullYear(),
      month: d.getMonth(),
      total_mad: 0,
      count: 0,
    }
  })
  factures.forEach(f => {
    if (!f.date_creation) return
    const d = new Date(f.date_creation)
    months.forEach(m => {
      if (d.getFullYear() === m.year && d.getMonth() === m.month) {
        m.total_mad += (f.montant_ttc && (f.devise === 'MAD' || !f.devise)) ? f.montant_ttc : 0
        m.count++
      }
    })
  })

  // Top fournisseurs — avec taux de rejet
  const fMap = {}
  factures.forEach(f => {
    if (!f.prestataire) return
    if (!fMap[f.prestataire]) fMap[f.prestataire] = { name: f.prestataire, count: 0, total: 0, rejected: 0 }
    fMap[f.prestataire].count++
    fMap[f.prestataire].total += f.montant_ttc || 0
    if (getStatut(f) === 'rejeté') fMap[f.prestataire].rejected++
  })
  const topFournisseurs = Object.values(fMap).sort((a, b) => b.count - a.count).slice(0, 5)

  // ── KPIs supplémentaires ──────────────────────────────────────────────────

  // Factures aujourd'hui
  const aujourdHui = factures.filter(f => {
    if (!f.date_creation) return false
    return new Date(f.date_creation).toDateString() === now.toDateString()
  }).length

  // Taux d'automatisation = % accepté sans réserve ni rejet
  const tauxAuto = total > 0 ? Math.round((nbAccepte / total) * 100) : 0

  // Score LLM moyen (champ confidence dans result_json)
  const confidenceScores = factures.flatMap(f => {
    try {
      const r = JSON.parse(f.result_json)
      const c = r?.perf?.confidence_llm ?? r?.data?.confidence
      return (c != null && c >= 0) ? [c] : []
    } catch { return [] }
  })
  const scoreLLM = confidenceScores.length > 0
    ? Math.round(confidenceScores.reduce((a, b) => a + b, 0) / confidenceScores.length)
    : null

  // Délai moyen soumission = moy(date_creation - date_facture) en jours
  const delais = factures.flatMap(f => {
    if (!f.date_facture || !f.date_creation) return []
    const df = new Date(f.date_facture)
    const dc = new Date(f.date_creation)
    const j  = Math.round((dc - df) / 86400000)
    return (j >= 0 && j < 3650) ? [j] : []
  })
  const delaiMoyen = delais.length > 0
    ? Math.round(delais.reduce((a, b) => a + b, 0) / delais.length)
    : null

  // ── Factures par jour (30 derniers jours) ────────────────────────────────
  const last30 = Array.from({ length: 30 }, (_, i) => {
    const d = new Date(now.getFullYear(), now.getMonth(), now.getDate() - (29 - i))
    return { label: d.toLocaleDateString('fr-FR', { day: '2-digit', month: '2-digit' }), count: 0, _date: d }
  })
  factures.forEach(f => {
    if (!f.date_creation) return
    const dc = new Date(f.date_creation)
    last30.forEach(d => {
      if (dc.toDateString() === d._date.toDateString()) d.count++
    })
  })

  // ── Champs manquants par champ (%) ───────────────────────────────────────
  const CHAMPS = [
    { key: 'prestataire',       label: 'Prestataire' },
    { key: 'date_facture',      label: 'Date facture' },
    { key: 'numero_facture',    label: 'N° facture' },
    { key: 'montant_ttc',       label: 'Montant TTC' },
    { key: 'tva',               label: 'TVA' },
    { key: 'montant_ht',        label: 'Montant HT' },
    { key: 'ice',               label: 'ICE' },
    { key: 'numero_engagement', label: 'N° engagement' },
  ]
  const champsManquants = CHAMPS.map(({ key, label }) => ({
    champ: label,
    taux:  total > 0
      ? Math.round(factures.filter(f => !f[key] && f[key] !== 0).length / total * 100)
      : 0,
  })).sort((a, b) => b.taux - a.taux)

  // ── Nouveaux KPIs métier ──────────────────────────────────────────────────

  // Taux de rejet
  const tauxRejet = total > 0 ? Math.round((nbRejete / total) * 100) : 0

  // Nombre de prestataires uniques
  const nbPrestataires = new Set(factures.map(f => f.prestataire).filter(Boolean)).size

  // Score global du système (0-100)
  // Formule : validation_auto * 0.4 + conformité * 0.3 + scoreLLM * 0.3
  // conformité = % factures non rejetées
  const conformite = total > 0 ? (nbAccepte + nbReserve) / total : 0
  const scoreGlobal = Math.round(
    (tauxAuto / 100) * 40 +
    conformite * 30 +
    ((scoreLLM != null ? scoreLLM / 100 : tauxAuto / 100)) * 30
  )

  // Gain de temps estimé (15 min manuel - 1 min auto = 14 min économisées / facture)
  const gainMinutes = total * 14
  const gainTempsLabel = gainMinutes >= 1440
    ? `${Math.round(gainMinutes / 1440)} jours`
    : gainMinutes >= 60
      ? `${Math.round(gainMinutes / 60)}h`
      : `${gainMinutes} min`

  // ── Métriques de performance (depuis result_json.perf) ───────────────────
  const perfData = factures.flatMap(f => {
    try {
      const r = JSON.parse(f.result_json)
      return r?.perf ? [r.perf] : []
    } catch { return [] }
  })

  const avgMs = (key) => {
    const vals = perfData.map(p => p[key]).filter(v => v != null && v >= 0)
    return vals.length > 0 ? Math.round(vals.reduce((a, b) => a + b, 0) / vals.length) : null
  }
  const maxMs = (key) => {
    const vals = perfData.map(p => p[key]).filter(v => v != null && v >= 0)
    return vals.length > 0 ? Math.max(...vals) : null
  }
  const fmtMs = (ms) => ms == null ? '—' : ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${ms}ms`

  const tempsMoyenOCR      = avgMs('t_ocr_ms')
  const tempsMoyenLLM      = avgMs('t_llm_ms')
  const tempsMoyenTotal    = avgMs('t_total_ms')
  const tempsMoyenResponse = avgMs('t_response_ms')
  const tempsMaxResponse   = maxMs('t_response_ms')
  const qualiteMoyOCR      = avgMs('ocr_chars')

  // Factures cette semaine
  const cetteSeamaine = factures.filter(f => {
    if (!f.date_creation) return false
    const d = new Date(f.date_creation)
    const diffDays = Math.floor((now - d) / 86400000)
    return diffDays < 7
  }).length

  // Données OCR vs LLM pour graphique (10 dernières avec perf)
  const perfByFact = factures
    .filter(f => { try { const r = JSON.parse(f.result_json); return r?.perf?.t_ocr_ms != null } catch { return false } })
    .slice(0, 10)
    .reverse()
    .map((f, i) => {
      try {
        const r = JSON.parse(f.result_json)
        return {
          label: `#${i + 1}`,
          ocr: +(r.perf.t_ocr_ms / 1000).toFixed(2),
          llm: +(r.perf.t_llm_ms / 1000).toFixed(2),
        }
      } catch { return null }
    })
    .filter(Boolean)

  // ── Top motifs de rejet ───────────────────────────────────────────────────
  const motifsMap = {}
  factures.forEach(f => {
    if (!f.motifs_rejet) return
    try {
      const motifs = JSON.parse(f.motifs_rejet)
      if (!Array.isArray(motifs)) return
      motifs.forEach(m => {
        // Garder uniquement la partie avant ':' ou '—' pour un label court
        const short = typeof m === 'string'
          ? m.split(/[:\u2014]/)[0].trim()
          : String(m)
        const key = short.length > 42 ? short.substring(0, 42) + '…' : short
        motifsMap[key] = (motifsMap[key] || 0) + 1
      })
    } catch {}
  })
  const topMotifs = Object.entries(motifsMap)
    .map(([motif, count]) => ({ motif, count }))
    .sort((a, b) => b.count - a.count)
    .slice(0, 6)

  return (
    <div className="p-6 space-y-6">

      {/* Bannière DB hors ligne */}
      {dbError && (
        <div className="flex items-start gap-3 p-4 rounded-xl bg-yellow-50 border border-yellow-300 text-yellow-800 text-sm">
          <AlertTriangle size={18} className="flex-shrink-0 mt-0.5 text-yellow-600" />
          <div>
            <span className="font-semibold">Base de données inaccessible</span>
            {' — '}Les données affichées proviennent de la session en cours uniquement. Les analyses seront perdues au rechargement de la page.
          </div>
        </div>
      )}

      {/* KPI cards — ligne 1 : volumes */}
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
        <KPICard Icon={FileText}    label="Total factures"        value={total}        color="bg-blue-600"   />
        <KPICard Icon={CalendarDays} label="Factures aujourd'hui" value={aujourdHui}   color="bg-purple-500" />
        <KPICard Icon={CheckCircle} label="Validées ce mois"      value={acceptesMois} color="bg-green-600"  />
        <KPICard Icon={XCircle}     label="Rejetées ce mois"      value={rejetesMois}  color="bg-red-500"    />
      </div>

      {/* KPI cards — ligne 2 : performance */}
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
        <KPICard Icon={Zap}   label="Taux d'automatisation"  value={`${tauxAuto}%`}                                        color="bg-indigo-500" />
        <KPICard Icon={Star}  label="Score LLM moyen"        value={scoreLLM != null ? `${scoreLLM}%` : '—'}               color="bg-pink-500"   />
        <KPICard Icon={Clock} label="Délai moyen soumission" value={delaiMoyen != null ? `${delaiMoyen}j` : '—'}           color="bg-teal-500"   />
        <KPICard Icon={Clock} label="À vérifier ce mois"     value={factures.filter(f => getStatut(f) === 'accepté_avec_réserve' && cesMois(f)).length} color="bg-orange-500" />
      </div>

      {/* KPI cards — ligne 3 : qualité & impact */}
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
        <KPICard
          Icon={Award}
          label="Score global du système"
          value={`${scoreGlobal} / 100`}
          color="bg-violet-600"
          sub="Validation × 0.4 + Conformité × 0.3 + LLM × 0.3"
        />
        <KPICard
          Icon={Timer}
          label="Gain de temps estimé"
          value={gainTempsLabel}
          color="bg-emerald-600"
          sub="14 min/facture économisées vs manuel "
        />
        <KPICard
          Icon={XCircle}
          label="Taux de rejet"
          value={`${tauxRejet}%`}
          color="bg-red-400"
          sub={`${nbRejete} facture(s) rejetée(s)`}
        />
        <KPICard
          Icon={Users}
          label="Prestataires actifs"
          value={nbPrestataires}
          color="bg-cyan-600"
          sub="Fournisseurs uniques"
        />
      </div>

      {/* KPI cards — ligne 4 : performances techniques */}
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-5 gap-4">
        <KPICard
          Icon={Clock}
          label="Temps de réponse moyen"
          value={fmtMs(tempsMoyenResponse)}
          color="bg-slate-600"
          sub={tempsMaxResponse != null ? `Max : ${fmtMs(tempsMaxResponse)}` : 'upload → réponse complète'}
        />
        <KPICard
          Icon={Clock}
          label="Temps traitement pur"
          value={fmtMs(tempsMoyenTotal)}
          color="bg-slate-400"
          sub="OCR + LLM + Vision (sans DB)"
        />
        <KPICard
          Icon={Zap}
          label="Temps moyen OCR"
          value={fmtMs(tempsMoyenOCR)}
          color="bg-sky-500"
          sub="Extraction du texte PDF"
        />
        <KPICard
          Icon={Activity}
          label="Temps moyen LLM"
          value={fmtMs(tempsMoyenLLM)}
          color="bg-violet-500"
          sub="Appel Gemini (analyse)"
        />
        <KPICard
          Icon={AlignLeft}
          label="Qualité texte OCR"
          value={qualiteMoyOCR != null ? `${qualiteMoyOCR} car.` : '—'}
          color="bg-amber-500"
          sub={`Cette semaine : ${cetteSeamaine} facture(s)`}
        />
      </div>

      {/* Montants */}
      <div className="grid grid-cols-1 gap-4">
        <div className="card">
          <p className="text-sm text-gray-500 mb-1">Total facturé (MAD)</p>
          <p className="text-2xl font-bold text-gray-900">
            {new Intl.NumberFormat('fr-MA', { maximumFractionDigits: 0 }).format(totalMAD)} DH
          </p>
        </div>
      </div>

      {/* Graphiques */}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">

        {/* Pie — répartition statuts */}
        <div className="card">
          <h2 className="font-semibold mb-4 text-gray-900">Répartition par statut</h2>
          {total === 0 ? (
            <div className="h-64 flex items-center justify-center text-gray-400 text-sm">
              Aucune donnée disponible
            </div>
          ) : (
            <ResponsiveContainer width="100%" height={280}>
              <PieChart>
                <Pie
                  data={pieData}
                  dataKey="value"
                  nameKey="name"
                  cx="50%" cy="45%"
                  outerRadius={85}
                  label={({ percent }) => `${(percent * 100).toFixed(0)}%`}
                  labelLine={false}
                >
                  {pieData.map((entry, i) => <Cell key={i} fill={entry.fill} />)}
                </Pie>
                <Legend
                  verticalAlign="bottom"
                  height={36}
                  formatter={(value) => <span className="text-sm text-gray-700">{value}</span>}
                />
                <Tooltip formatter={(v, name) => [v, name]} />
              </PieChart>
            </ResponsiveContainer>
          )}
        </div>

        {/* Bar — montants mensuels */}
        <div className="card">
          <h2 className="font-semibold mb-4 text-gray-900">Montants mensuels (MAD)</h2>
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={months}>
              <XAxis dataKey="period" tick={{ fontSize: 12 }} />
              <YAxis tick={{ fontSize: 12 }} />
              <Tooltip
                formatter={(v) => new Intl.NumberFormat('fr-MA').format(Number(v)) + ' DH'}
              />
              <Bar dataKey="total_mad" fill="#2563eb" radius={[4, 4, 0, 0]} name="MAD" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Graphiques — ligne 2 */}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">

        {/* Line chart — factures par jour */}
        <div className="card">
          <h2 className="font-semibold mb-4 text-gray-900">Factures par jour (30 derniers jours)</h2>
          <ResponsiveContainer width="100%" height={240}>
            <LineChart data={last30} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
              <XAxis dataKey="label" tick={{ fontSize: 10 }} interval={4} />
              <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
              <Tooltip formatter={(v) => [v, 'Factures']} />
              <Line type="monotone" dataKey="count" stroke="#2563eb" strokeWidth={2} dot={false} name="Factures" />
            </LineChart>
          </ResponsiveContainer>
        </div>

        {/* Bar chart horizontal — champs manquants */}
        <div className="card">
          <h2 className="font-semibold mb-4 text-gray-900">Complétude des données extraites</h2>
          {total === 0 ? (
            <div className="h-60 flex items-center justify-center text-gray-400 text-sm">Aucune donnée</div>
          ) : (
            <ResponsiveContainer width="100%" height={240}>
              <BarChart data={champsManquants} layout="vertical" margin={{ left: 20, right: 20 }}>
                <XAxis type="number" domain={[0, 100]} tick={{ fontSize: 11 }} unit="%" />
                <YAxis type="category" dataKey="champ" tick={{ fontSize: 11 }} width={100} />
                <Tooltip formatter={(v) => [`${v}%`, 'Manquant']} />
                <Bar dataKey="taux" fill="#f59e0b" radius={[0, 4, 4, 0]} name="Taux manquant" />
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>

      {/* Graphiques — ligne 3 : Top motifs de rejet */}
      <div className="card">
        <h2 className="font-semibold mb-4 text-gray-900">Top motifs de rejet</h2>
        {topMotifs.length === 0 ? (
          <div className="h-48 flex items-center justify-center text-gray-400 text-sm">
            Aucune facture rejetée
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={Math.max(200, topMotifs.length * 48)}>
            <BarChart data={topMotifs} layout="vertical" margin={{ left: 16, right: 40, top: 4, bottom: 4 }}>
              <XAxis type="number" allowDecimals={false} tick={{ fontSize: 11 }} />
              <YAxis type="category" dataKey="motif" tick={{ fontSize: 11 }} width={220} />
              <Tooltip formatter={(v) => [v, 'Occurrences']} />
              <Bar dataKey="count" fill="#ef4444" radius={[0, 4, 4, 0]} name="Occurrences">
                {topMotifs.map((_, i) => (
                  <Cell key={i} fill={i === 0 ? '#dc2626' : i === 1 ? '#ef4444' : '#f87171'} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        )}
      </div>

      {/* Graphique — Temps de traitement OCR vs LLM */}
      <div className="card">
        <h2 className="font-semibold mb-1 text-gray-900">Temps de traitement OCR vs LLM</h2>
        <p className="text-xs text-gray-400 mb-4">10 dernières analyses (en secondes)</p>
        {perfByFact.length === 0 ? (
          <div className="h-52 flex items-center justify-center text-gray-400 text-sm">
            Aucune donnée de performance disponible — les prochaines analyses alimenteront ce graphique
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={perfByFact} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
              <XAxis dataKey="label" tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} unit="s" />
              <Tooltip formatter={(v, name) => [`${v}s`, name === 'ocr' ? 'OCR' : 'LLM (Gemini)']} />
              <Legend formatter={(v) => v === 'ocr' ? 'OCR' : 'LLM (Gemini)'} />
              <Bar dataKey="ocr" fill="#0ea5e9" radius={[4, 4, 0, 0]} name="ocr" />
              <Bar dataKey="llm" fill="#8b5cf6" radius={[4, 4, 0, 0]} name="llm" />
            </BarChart>
          </ResponsiveContainer>
        )}
      </div>

      {/* Top fournisseurs */}
      <div className="card">
        <h2 className="font-semibold mb-4 text-gray-900">Top fournisseurs</h2>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-gray-500 border-b">
                <th className="pb-3 font-medium">Fournisseur</th>
                <th className="pb-3 font-medium">Nb factures</th>
                <th className="pb-3 font-medium">Total (MAD)</th>
                <th className="pb-3 font-medium">Taux de rejet</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {topFournisseurs.map((s, i) => {
                const taux = s.count > 0 ? Math.round(s.rejected / s.count * 100) : 0
                return (
                  <tr key={i}>
                    <td className="py-3 font-medium text-gray-900">{s.name}</td>
                    <td className="py-3 text-gray-600">{s.count}</td>
                    <td className="py-3 text-gray-600">
                      {new Intl.NumberFormat('fr-MA').format(s.total)} DH
                    </td>
                    <td className="py-3">
                      <span className={`text-xs font-semibold px-2 py-1 rounded-full
                        ${taux === 0 ? 'bg-green-100 text-green-700'
                          : taux < 30 ? 'bg-yellow-100 text-yellow-700'
                          : 'bg-red-100 text-red-700'}`}>
                        {taux}%
                      </span>
                    </td>
                  </tr>
                )
              })}
              {topFournisseurs.length === 0 && (
                <tr>
                  <td colSpan={4} className="py-8 text-center text-gray-400">Aucune donnée</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}

import { FileText, Clock, CheckCircle, XCircle, AlertTriangle, CalendarDays, Zap, Star } from 'lucide-react'
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

function KPICard({ Icon, label, value, color }) {
  return (
    <div className="card flex items-center gap-4">
      <div className={`p-3 rounded-xl ${color}`}>
        <Icon size={22} className="text-white" />
      </div>
      <div>
        <p className="text-2xl font-bold text-gray-900">{value}</p>
        <p className="text-sm text-gray-500">{label}</p>
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
  const totalUSD = factures
    .filter(f => f.devise === 'USD' && f.montant_ttc)
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

  // Top fournisseurs
  const fMap = {}
  factures.forEach(f => {
    if (!f.prestataire) return
    if (!fMap[f.prestataire]) fMap[f.prestataire] = { name: f.prestataire, count: 0, total: 0 }
    fMap[f.prestataire].count++
    fMap[f.prestataire].total += f.montant_ttc || 0
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
      const c = r?.data?.confidence
      return (c != null && c > 0) ? [c] : []
    } catch { return [] }
  })
  const scoreLLM = confidenceScores.length > 0
    ? Math.round(confidenceScores.reduce((a, b) => a + b, 0) / confidenceScores.length * 100)
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
          <h2 className="font-semibold mb-4 text-gray-900">Champs manquants par champ (%)</h2>
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
              </tr>
            </thead>
            <tbody className="divide-y">
              {topFournisseurs.map((s, i) => (
                <tr key={i}>
                  <td className="py-3 font-medium text-gray-900">{s.name}</td>
                  <td className="py-3 text-gray-600">{s.count}</td>
                  <td className="py-3 text-gray-600">
                    {new Intl.NumberFormat('fr-MA').format(s.total)} DH
                  </td>
                </tr>
              ))}
              {topFournisseurs.length === 0 && (
                <tr>
                  <td colSpan={3} className="py-8 text-center text-gray-400">Aucune donnée</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}

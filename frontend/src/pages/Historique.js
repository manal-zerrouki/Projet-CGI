import { useState } from 'react'
import { Search, AlertTriangle } from 'lucide-react'
import { StatusBadge } from '../components/StatusBadge'

function getStatut(f) {
  if (f.statut_validation) return f.statut_validation
  const exc = f.exception
  if (!exc || exc === '[]' || exc === 'None' || exc === 'null') return 'accepté'
  return 'accepté_avec_réserve'
}

// Parse une date ISO "YYYY-MM-DD" sans décalage timezone (évite le bug UTC → J-1)
function fmtISODate(str) {
  if (!str) return '—'
  // Format YYYY-MM-DD depuis la DB
  if (/^\d{4}-\d{2}-\d{2}$/.test(str)) {
    const [y, m, d] = str.split('-')
    return new Date(+y, +m - 1, +d).toLocaleDateString('fr-FR')
  }
  // Format DD-MM-YYYY depuis l'OCR
  if (/^\d{2}-\d{2}-\d{4}$/.test(str)) {
    const [d, m, y] = str.split('-')
    return new Date(+y, +m - 1, +d).toLocaleDateString('fr-FR')
  }
  return str
}

function hasAlertes(f) {
  const exc = f.exception
  return exc && exc !== '[]' && exc !== 'None' && exc !== 'null'
}

export default function Historique({ factures, dbError }) {
  const [search,       setSearch]       = useState('')
  const [filterStatut, setFilterStatut] = useState('')
  const [dateFrom,     setDateFrom]     = useState('')
  const [dateTo,       setDateTo]       = useState('')
  const [dateType,     setDateType]     = useState('creation') // 'creation' | 'facture'
  const [page,         setPage]         = useState(1)
  const PAGE_SIZE = 20

  const filtered = factures.filter(f => {
    const q = search.toLowerCase()
    const matchSearch = !search
      || (f.prestataire    || '').toLowerCase().includes(q)
      || (f.numero_facture || '').toLowerCase().includes(q)
    const matchStatut = !filterStatut || getStatut(f) === filterStatut

    // Date filtrée selon le type choisi
    let dateVal = null
    if (dateType === 'creation') {
      dateVal = f.date_creation ? new Date(f.date_creation) : null
    } else {
      // date_facture au format YYYY-MM-DD → parser sans décalage UTC
      if (f.date_facture) {
        const [y, m, d] = f.date_facture.split('-')
        dateVal = new Date(+y, +m - 1, +d)
      }
    }
    const matchFrom = !dateFrom || (dateVal && dateVal >= new Date(dateFrom))
    const matchTo   = !dateTo   || (dateVal && dateVal <= new Date(dateTo + 'T23:59:59'))
    return matchSearch && matchStatut && matchFrom && matchTo
  })

  const paginated = filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE)
  const totalPages = Math.ceil(filtered.length / PAGE_SIZE)

  const resetFilters = () => {
    setSearch(''); setFilterStatut(''); setDateFrom(''); setDateTo(''); setDateType('creation'); setPage(1)
  }

  return (
    <div className="p-6 space-y-5">

      {/* Bannière DB hors ligne */}
      {dbError && (
        <div className="flex items-start gap-3 p-4 rounded-xl bg-yellow-50 border border-yellow-300 text-yellow-800 text-sm">
          <AlertTriangle size={18} className="flex-shrink-0 mt-0.5 text-yellow-600" />
          <div>
            <span className="font-semibold">Base de données inaccessible</span>
            {' — '}Les données affichées proviennent de la session en cours uniquement.
          </div>
        </div>
      )}

      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Historique</h1>
        <p className="text-gray-500 text-sm">{filtered.length} facture(s) trouvée(s)</p>
      </div>

      {/* Filtres */}
      <div className="card flex gap-4 flex-wrap items-end p-4">
        <div className="flex-1 min-w-48 relative">
          <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
          <input
            className="input pl-9"
            placeholder="Fournisseur ou N° facture..."
            value={search}
            onChange={e => { setSearch(e.target.value); setPage(1) }}
          />
        </div>

        <div className="min-w-44">
          <select
            value={filterStatut}
            onChange={e => { setFilterStatut(e.target.value); setPage(1) }}
            className="input"
          >
            <option value="">Tous les statuts</option>
            <option value="accepté">Validée</option>
            <option value="accepté_avec_réserve">Avec réserve</option>
            <option value="rejeté">Rejetée</option>
          </select>
        </div>

        {/* Toggle type de date */}
        <div className="flex flex-col gap-1">
          <label className="label text-xs">Filtrer par</label>
          <div className="flex rounded-lg border border-gray-200 overflow-hidden text-xs font-medium">
            <button
              onClick={() => { setDateType('creation'); setPage(1) }}
              className={`px-3 py-2 transition-colors ${dateType === 'creation' ? 'bg-blue-600 text-white' : 'bg-white text-gray-500 hover:bg-gray-50'}`}
            >
              Date traitement
            </button>
            <button
              onClick={() => { setDateType('facture'); setPage(1) }}
              className={`px-3 py-2 transition-colors ${dateType === 'facture' ? 'bg-blue-600 text-white' : 'bg-white text-gray-500 hover:bg-gray-50'}`}
            >
              Date facture
            </button>
          </div>
        </div>

        <div className="min-w-36">
          <label className="label text-xs">Du</label>
          <input
            type="date" value={dateFrom}
            onChange={e => { setDateFrom(e.target.value); setPage(1) }}
            className="input"
          />
        </div>

        <div className="min-w-36">
          <label className="label text-xs">Au</label>
          <input
            type="date" value={dateTo}
            onChange={e => { setDateTo(e.target.value); setPage(1) }}
            className="input"
          />
        </div>

        {(search || filterStatut || dateFrom || dateTo) && (
          <button onClick={resetFilters} className="btn-secondary text-sm whitespace-nowrap">
            Réinitialiser
          </button>
        )}
      </div>

      {/* Table */}
      <div className="card p-0 overflow-hidden">
        <div className="overflow-x-auto">
        <table className="w-full text-sm min-w-[860px]">
          <thead className="bg-gray-50 border-b">
            <tr className="text-left text-gray-500">
              <th className="px-6 py-4 font-medium">N° Facture</th>
              <th className="px-6 py-4 font-medium">Prestataire</th>
              <th className="px-6 py-4 font-medium">Date facture</th>
              <th className="px-6 py-4 font-medium">Montant TTC</th>
              <th className="px-6 py-4 font-medium">Devise</th>
              <th className="px-6 py-4 font-medium">Statut</th>
              <th className="px-6 py-4 font-medium">Alertes</th>
              <th className="px-6 py-4 font-medium">Traitée le</th>
            </tr>
          </thead>
          <tbody className="divide-y">
            {paginated.length === 0 && (
              <tr>
                <td colSpan={8} className="py-12 text-center text-gray-400">
                  Aucune facture trouvée
                </td>
              </tr>
            )}
            {paginated.map((f, i) => (
              <tr key={i} className="hover:bg-gray-50 transition-colors">
                <td className="px-6 py-4 font-mono text-xs text-gray-700">
                  {f.numero_facture || '—'}
                </td>
                <td className="px-6 py-4 text-gray-800 max-w-xs truncate">
                  {f.prestataire || '—'}
                </td>
                <td className="px-6 py-4 text-gray-500">
                  {fmtISODate(f.date_facture)}
                </td>
                <td className="px-6 py-4 font-medium text-gray-900">
                  {f.montant_ttc != null
                    ? new Intl.NumberFormat('fr-MA', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(f.montant_ttc)
                    : '—'}
                </td>
                <td className="px-6 py-4 text-gray-500">{f.devise || '—'}</td>
                <td className="px-6 py-4">
                  <StatusBadge status={getStatut(f)} />
                </td>
                <td className="px-6 py-4">
                  {hasAlertes(f) && (
                    <AlertTriangle size={16} className="text-yellow-500" title="Réserves enregistrées" />
                  )}
                </td>
                <td className="px-6 py-4 text-gray-400 text-xs whitespace-nowrap">
                  {f.date_creation
                    ? new Date(f.date_creation).toLocaleString('fr-FR')
                    : '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        </div>

        {/* Pagination */}
        <div className="flex items-center justify-between px-6 py-4 border-t bg-gray-50">
          <button
            onClick={() => setPage(p => Math.max(1, p - 1))}
            disabled={page === 1}
            className="btn-secondary text-sm"
          >
            Précédent
          </button>
          <span className="text-sm text-gray-500">
            Page {page}{totalPages > 1 ? ` / ${totalPages}` : ''}
            {' '}· {filtered.length} résultat{filtered.length !== 1 ? 's' : ''}
          </span>
          <button
            onClick={() => setPage(p => p + 1)}
            disabled={page >= totalPages}
            className="btn-secondary text-sm"
          >
            Suivant
          </button>
        </div>
      </div>
    </div>
  )
}

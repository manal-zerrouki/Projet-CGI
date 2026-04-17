import { useState, useEffect, useRef } from 'react'
import Sidebar from './components/Sidebar'
import TopBar from './components/TopBar'
import Dashboard from './pages/Dashboard'
import Factures from './pages/Factures'
import Historique from './pages/Historique'
import Fournisseurs from './pages/Fournisseurs'
import './App.css'

const API_URL = process.env.REACT_APP_API_URL || 'http://127.0.0.1:8000'

// Convertit un résultat d'analyse en entrée format DB (pour affichage local immédiat)
function resultToFacture(result) {
  const d = result?.data ?? result
  const toISO = (str) => {
    if (!str) return null
    if (/^\d{2}-\d{2}-\d{4}$/.test(str)) {
      const [day, mon, yr] = str.split('-')
      return `${yr}-${mon}-${day}`
    }
    return str
  }
  return {
    numero_facture:    d?.numero_facture    ?? null,
    prestataire:       d?.prestataire       ?? null,
    ice:               d?.ice               ?? null,
    date_facture:      toISO(d?.date_facture),
    numero_engagement: d?.numero_engagement ?? null,
    montant_ht:        d?.montant_ht        ?? null,
    tva:               d?.tva               ?? null,
    montant_ttc:       d?.montant_ttc       ?? null,
    devise:            d?.devise            ?? null,
    statut_validation: result?.validation   ?? null,
    exception:         JSON.stringify(result?.exceptions ?? []),
    date_creation:     new Date().toISOString(),
    _local:            true,
  }
}

export default function App() {
  const [activePage, setActivePage] = useState('dashboard')
  const [factures,   setFactures]   = useState([])
  const [dbError,    setDbError]    = useState(null)
  const [lastResult, setLastResult] = useState(null)

  // Queue persistante — survit à la navigation
  const [queue, setQueue] = useState([])
  const processingRef = useRef(false)

  const fetchFactures = (opts = {}) => {
    fetch(`${API_URL}/factures`)
      .then(res => res.json())
      .then(data => {
        if (Array.isArray(data) && data.length > 0) {
          setDbError(null)
          // Garder les entrées locales pas encore en DB (par numéro de facture)
          setFactures(prev => {
            const dbKeys = new Set(data.map(f => f.numero_facture).filter(Boolean))
            const localOnly = prev.filter(f => f._local && !dbKeys.has(f.numero_facture))
            return [...data, ...localOnly]
          })

          // ── Restauration depuis DB au chargement initial ──────────────────
          // Reconstruit la file de traitement à partir des factures en DB
          // (items virtuels — pas de fichier PDF, juste les résultats JSON)
          if (opts.restoreQueue) {
            const withResult = data.filter(f => f.result_json)
            if (withResult.length > 0) {
              const virtualItems = withResult.map(f => {
                let result = null
                try { result = JSON.parse(f.result_json) } catch {}
                return {
                  id:       f.numero_facture,
                  virtual:  true,
                  label:    f.prestataire   || f.numero_facture || 'Facture',
                  sublabel: f.numero_facture || '',
                  status:   'done',
                  result,
                }
              })
              setQueue(virtualItems)
              // Dernier résultat = la facture la plus récente
              if (virtualItems[0]?.result) setLastResult(virtualItems[0].result)
            }
          }
        } else if (data?.error) {
          setDbError(data.error)
        }
      })
      .catch(err => {
        console.error('Fetch /factures error:', err)
        setDbError(err.message)
      })
  }

  // Chargement initial — restaure aussi la file de traitement depuis la DB
  useEffect(() => { fetchFactures({ restoreQueue: true }) }, [])

  // Re-fetch à chaque navigation vers dashboard ou historique
  useEffect(() => {
    if (activePage === 'dashboard' || activePage === 'historique') {
      fetchFactures()
    }
  }, [activePage])

  const processQueue = async (currentQueue) => {
    if (processingRef.current) return
    const waiting = currentQueue.filter(i => i.status === 'waiting')
    if (waiting.length === 0) return

    processingRef.current = true

    for (const item of waiting) {
      setQueue(prev => prev.map(i => i.id === item.id ? { ...i, status: 'processing' } : i))
      try {
        const fd = new FormData()
        fd.append('file', item.file)
        const res  = await fetch(`${API_URL}/analyze`, { method: 'POST', body: fd })
        const data = await res.json().catch(() => null)
        if (!res.ok) throw new Error(data?.detail || `Erreur HTTP ${res.status}`)

        // ── Mise à jour immédiate du state local (indépendant de la DB) ──
        const localFacture = resultToFacture(data)
        setFactures(prev => {
          // Upsert : si même numéro existe déjà, on le remplace
          const key = localFacture.numero_facture
          const base = key ? prev.filter(f => f.numero_facture !== key) : prev
          return [localFacture, ...base]
        })

        setQueue(prev => prev.map(i => i.id === item.id ? { ...i, status: 'done', result: data } : i))
        setLastResult(data)

        // Synchronisation DB en arrière-plan (remplacera l'entrée locale si succès)
        fetchFactures()
      } catch (e) {
        setQueue(prev => prev.map(i => i.id === item.id ? { ...i, status: 'error', error: e.message } : i))
      }
    }

    processingRef.current = false
  }

  const retryQueueItem = (id) => {
    setQueue(prev => {
      const updated = prev.map(i => i.id === id ? { ...i, status: 'waiting', error: null } : i)
      setTimeout(() => processQueue(updated), 0)
      return updated
    })
  }

  const handleAddFiles = (files) => {
    const newItems = files.map(f => ({
      id: Date.now() + Math.random(),
      file: f,
      status: 'waiting',
      result: null,
      error: null,
    }))
    setQueue(prev => {
      const updated = [...prev, ...newItems]
      setTimeout(() => processQueue(updated), 0)
      return updated
    })
  }

  const renderPage = () => {
    switch (activePage) {
      case 'dashboard':
        return <Dashboard factures={factures} dbError={dbError} />
      case 'factures':
        return (
          <Factures
            lastResult={lastResult}
            queue={queue}
            setQueue={setQueue}
            handleAddFiles={handleAddFiles}
            retryQueueItem={retryQueueItem}
          />
        )
      case 'historique':
        return <Historique factures={factures} dbError={dbError} />
      case 'fournisseurs':
        return <Fournisseurs />
      default:
        return <Dashboard factures={factures} dbError={dbError} />
    }
  }

  return (
    <div className="flex h-screen bg-gray-50">
      <Sidebar activePage={activePage} setActivePage={setActivePage} lastResult={lastResult} />
      <div className="flex flex-col flex-1 min-w-0 overflow-hidden">
        <TopBar activePage={activePage} />
        <main className="flex-1 overflow-auto">
          {renderPage()}
        </main>
      </div>
    </div>
  )
}

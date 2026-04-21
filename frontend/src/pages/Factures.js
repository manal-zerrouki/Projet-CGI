import { useState, useRef, useEffect } from 'react'
import { ArrowLeft, CheckCircle, AlertTriangle, XCircle, Copy, Upload, X, Clock, Save } from 'lucide-react'
import PdfPreview from './PdfPreview'

// ── Helpers ──────────────────────────────────────────────────────────────────

function fmtAmount(value, devise) {
  if (value == null) return null
  return new Intl.NumberFormat('fr-FR', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value) + ' ' + (devise || 'MAD')
}

function fmtDate(str) {
  if (!str) return null
  try { const [d, m, y] = str.split('-'); return new Date(y, m - 1, d).toLocaleDateString('fr-FR') }
  catch { return str }
}

// ── Statut pill ───────────────────────────────────────────────────────────────

function StatutPill({ statut }) {
  if (statut === 'accepté')
    return <span className="inline-flex items-center gap-1 px-3 py-1 rounded-full text-xs font-semibold bg-green-100 text-green-700"><CheckCircle size={12}/>Validée</span>
  if (statut === 'accepté_avec_réserve')
    return <span className="inline-flex items-center gap-1 px-3 py-1 rounded-full text-xs font-semibold bg-yellow-100 text-yellow-800"><AlertTriangle size={12}/>Sous réserve</span>
  if (statut === 'rejeté')
    return <span className="inline-flex items-center gap-1 px-3 py-1 rounded-full text-xs font-semibold bg-red-100 text-red-700"><XCircle size={12}/>Rejetée</span>
  return <span className="inline-flex items-center gap-1 px-3 py-1 rounded-full text-xs font-semibold bg-gray-100 text-gray-500"><Clock size={12}/>En cours</span>
}

// ── Ligne de champ ────────────────────────────────────────────────────────────

function FieldRow({ label, value, highlight, missing }) {
  const isEmpty = value == null || value === '' || value === false
  let display = value
  if (value === true)  display = '✓ Présent'
  if (value === false) display = '✗ Absent'

  return (
    <div className="flex items-center justify-between px-5 py-3 gap-4 odd:bg-white even:bg-gray-50 last:rounded-b-xl">
      <span className="text-sm text-gray-400 flex-shrink-0 w-44">{label}</span>
      {missing && isEmpty
        ? <span className="text-xs font-medium text-red-600 bg-red-50 border border-red-200 rounded-full px-3 py-0.5">Manquant</span>
        : <span className={`text-sm text-right leading-snug
            ${highlight ? 'font-semibold text-gray-900' : 'text-gray-700'}
            ${isEmpty ? 'text-gray-300' : ''}
            ${value === true ? 'text-green-600 font-medium' : ''}
            ${value === false ? 'text-red-500' : ''}`}>
            {isEmpty ? '—' : String(display)}
          </span>
      }
    </div>
  )
}

function Section({ title, icon, children }) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
      <div className="flex items-center gap-2 px-5 py-3.5 border-b border-gray-100 bg-gray-50">
        <span>{icon}</span>
        <h3 className="text-sm font-semibold text-gray-700">{title}</h3>
      </div>
      <div>{children}</div>
    </div>
  )
}

// ── Bannière statut ───────────────────────────────────────────────────────────

function StatusBanner({ result }) {
  const v = result.validation
  if (v === 'accepté') return (
    <div className="flex items-start gap-3 p-4 rounded-xl bg-green-50 border-2 border-green-300">
      <CheckCircle size={22} className="text-green-600 flex-shrink-0 mt-0.5"/>
      <div>
        <p className="font-bold text-green-800">Facture validée automatiquement</p>
        <p className="text-green-700 text-sm mt-0.5">Toutes les vérifications obligatoires sont conformes.</p>
      </div>
    </div>
  )
  if (v === 'accepté_avec_réserve') return (
    <div className="flex items-start gap-3 p-4 rounded-xl bg-yellow-50 border-2 border-yellow-300">
      <AlertTriangle size={22} className="text-yellow-600 flex-shrink-0 mt-0.5"/>
      <div>
        <p className="font-bold text-yellow-800">Facture acceptée sous réserve</p>
        <p className="text-yellow-700 text-sm mt-0.5">
          {(result.warnings?.length || 0) + (result.exceptions?.length || 0)} point(s) à vérifier manuellement.
        </p>
        {result.warnings?.length > 0 && (
          <ul className="mt-2 space-y-0.5">
            {result.warnings.map((w, i) => <li key={i} className="text-sm text-yellow-700 flex items-start gap-1.5"><span className="mt-1 flex-shrink-0">·</span>{w}</li>)}
          </ul>
        )}
      </div>
    </div>
  )
  return (
    <div className="flex items-start gap-3 p-4 rounded-xl bg-red-50 border-2 border-red-300">
      <XCircle size={22} className="text-red-600 flex-shrink-0 mt-0.5"/>
      <div>
        <p className="font-bold text-red-800">Facture rejetée</p>
        <p className="text-red-700 text-sm mt-0.5">{result.motifs_rejet?.length || 0} motif(s) de rejet détecté(s).</p>
        {result.motifs_rejet?.length > 0 && (
          <ul className="mt-2 space-y-1">
            {result.motifs_rejet.map((r, i) => (
              <li key={i} className="flex items-start gap-2 text-sm text-red-700">
                <XCircle size={13} className="flex-shrink-0 mt-0.5"/>{r}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}

// ── Résultats d'une facture ───────────────────────────────────────────────────

function ResultView({ result, item, onBack }) {
  const [tab, setTab] = useState('data')
  const [openPanel, setOpenPanel] = useState(null)
  const [commentaire, setCommentaire] = useState('')
  const [savingComment, setSavingComment] = useState(false)
  const d = result?.data ?? result

  const API_URL = 'http://127.0.0.1:8000'
  const numero = d?.numero_facture

  const togglePanel = (key) => setOpenPanel(prev => prev === key ? null : key)

  const panels = [
    {
      key:   'erreurs',
      count: result.motifs_rejet?.length ?? 0,
      label: 'Erreurs bloquantes',
      color: 'text-red-500',
      bg:    'bg-red-50 border-red-200',
      items: result.motifs_rejet ?? [],
      icon:  <XCircle size={13} className="flex-shrink-0 text-red-500 mt-0.5"/>,
      empty: 'Aucune erreur bloquante.',
    },
    {
      key:   'warnings',
      count: result.warnings?.length ?? 0,
      label: 'Avertissements',
      color: 'text-yellow-500',
      bg:    'bg-yellow-50 border-yellow-200',
      items: result.warnings ?? [],
      icon:  <AlertTriangle size={13} className="flex-shrink-0 text-yellow-500 mt-0.5"/>,
      empty: 'Aucun avertissement.',
    },
    {
      key:   'exceptions',
      count: result.exceptions?.length ?? 0,
      label: 'Exceptions',
      color: 'text-blue-500',
      bg:    'bg-blue-50 border-blue-200',
      items: result.exceptions ?? [],
      icon:  <AlertTriangle size={13} className="flex-shrink-0 text-blue-500 mt-0.5"/>,
      empty: 'Aucune exception.',
    },
  ]

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <button onClick={onBack} className="text-gray-400 hover:text-gray-600 transition-colors" title="Retour">
            <ArrowLeft size={20}/>
          </button>
          <div>
            <div className="flex items-center gap-3">
              <h2 className="text-lg font-bold text-gray-900">{d?.prestataire || 'Facture analysée'}</h2>
              <StatutPill statut={result.validation}/>
            </div>
            {d?.numero_facture && <p className="text-xs text-gray-400 font-mono mt-0.5">{d.numero_facture}</p>}
          </div>
        </div>
        <button onClick={onBack} className="btn-secondary text-sm">Nouvelle analyse</button>
      </div>

      {/* Bannière */}
      <StatusBanner result={result}/>

      {/* Compteurs cliquables */}
      <div className="grid grid-cols-3 gap-4">
        {panels.map(p => (
          <button
            key={p.key}
            onClick={() => togglePanel(p.key)}
            className={`card text-center py-4 transition-all hover:shadow-md
              ${openPanel === p.key ? 'ring-2 ring-offset-1 ring-gray-300' : ''}`}
          >
            <p className={`text-2xl font-bold ${p.color}`}>{p.count}</p>
            <p className="text-xs text-gray-500 mt-1">{p.label}</p>
            <p className="text-xs text-gray-300 mt-0.5">{openPanel === p.key ? '▲ Masquer' : '▼ Détail'}</p>
          </button>
        ))}
      </div>

      {/* Panneau de détail */}
      {openPanel && (() => {
        const p = panels.find(x => x.key === openPanel)
        return (
          <div className={`rounded-xl border p-4 space-y-2 ${p.bg}`}>
            <div className="flex items-center justify-between mb-1">
              <p className="text-sm font-semibold text-gray-800">{p.label}</p>
              <button onClick={() => setOpenPanel(null)} className="text-gray-400 hover:text-gray-600 text-xs">✕</button>
            </div>
            {p.items.length === 0
              ? <p className="text-sm text-gray-400 italic">{p.empty}</p>
              : <ul className="space-y-1.5">
                  {p.items.map((item, i) => (
                    <li key={i} className="flex items-start gap-2 text-sm text-gray-700">
                      {p.icon}{item}
                    </li>
                  ))}
                </ul>
            }
          </div>
        )
      })()}

      {/* Tabs */}
      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        <div className="flex border-b border-gray-200 px-2">
          {[['data','Données extraites'],['ocr','Aperçu OCR'],['json','JSON']].map(([id, label]) => (
            <button key={id} onClick={() => setTab(id)}
              className={`px-5 py-3.5 text-sm font-medium transition-colors border-b-2 -mb-px
                ${tab === id ? 'text-blue-600 border-blue-600' : 'text-gray-500 border-transparent hover:text-gray-700'}`}>
              {label}
            </button>
          ))}
        </div>

        <div className="p-6">
          {/* ── Données extraites ── */}
          {tab === 'data' && (
            <div className="grid grid-cols-1 xl:grid-cols-2 gap-8">
              <div className="xl:max-h-[600px] xl:overflow-auto">
                <Section title="Facture originale" icon="🖼️">
                  <PdfPreview file={item.file} className="w-full h-96 xl:h-[500px]" />
                </Section>
              </div>
              <div>
                <Section title="Identification" icon="🏢">
                  <FieldRow label="Prestataire"         value={d?.prestataire}                   missing highlight/>
                  <FieldRow label="ICE"                 value={d?.ice}                           missing/>
                  <FieldRow label="N° Facture"          value={d?.numero_facture}                missing highlight/>
                  <FieldRow label="N° Engagement"   value={d?.numero_engagement}             missing/>
                  <FieldRow label="Date de facture"     value={fmtDate(d?.date_facture)}         missing/>
                  <FieldRow label="Date d'échéance"     value={fmtDate(d?.date_echeance)}/>
                  <FieldRow label="Cachet / Signature"  value={d?.cachet_signature}              missing/>
                </Section>

                <Section title="Montants" icon="💰">
                  <FieldRow label="Montant HT"       value={fmtAmount(d?.montant_ht, d?.devise)}       missing highlight/>
                  <FieldRow label="TVA"              value={fmtAmount(d?.tva, d?.devise)}/>
                  <FieldRow label="Taux TVA"         value={d?.taux_tva != null ? `${d.taux_tva} %` : null}/>
                  <FieldRow label="Total TTC"        value={fmtAmount(d?.montant_ttc, d?.devise)}      missing highlight/>
                  <FieldRow label="Retenue à la source" value={fmtAmount(d?.retenue_source, d?.devise)}/>
                  <FieldRow label="Net à payer"      value={fmtAmount(d?.net_a_payer, d?.devise)}      highlight/>
                  <FieldRow label="Devise"           value={d?.devise}/>
                </Section>

                <Section title="TTC en lettres" icon="📝">
                  {d?.montant_ttc_lettres ? (() => {
                    const hasMismatch = (result.motifs_rejet || []).some(m =>
                      m.toLowerCase().includes('en lettres')
                    )
                    const isUnparseable = (result.warnings || []).some(w =>
                      w.toLowerCase().includes('en lettres') && w.toLowerCase().includes('non convertible')
                    )
                    return (
                      <div className="px-5 py-4 space-y-3">
                        <p className="text-sm italic text-gray-700 leading-relaxed">
                          {d.montant_ttc_lettres}
                        </p>
                        <div className={`flex items-center gap-2 text-xs font-medium px-3 py-2 rounded-lg
                          ${hasMismatch
                            ? 'bg-red-50 text-red-700 border border-red-200'
                            : isUnparseable
                              ? 'bg-yellow-50 text-yellow-700 border border-yellow-200'
                              : 'bg-green-50 text-green-700 border border-green-200'
                          }`}>
                          {hasMismatch ? (
                            <><XCircle size={13} className="flex-shrink-0"/>
                              Incohérence avec le TTC chiffré ({fmtAmount(d?.montant_ttc, d?.devise)})</>
                          ) : isUnparseable ? (
                            <><AlertTriangle size={13} className="flex-shrink-0"/>
                              Vérification automatique impossible — contrôle manuel requis</>
                          ) : (
                            <><CheckCircle size={13} className="flex-shrink-0"/>
                              Correspond au TTC chiffré : {fmtAmount(d?.montant_ttc, d?.devise)}</>
                          )}
                        </div>
                      </div>
                    )
                  })() : (
                    <div className="px-5 py-4">
                      <p className="text-sm text-yellow-600 flex items-center gap-2">
                        <AlertTriangle size={14} className="flex-shrink-0"/>
                        Non présent sur la facture
                      </p>
                    </div>
                  )}
                </Section>

                <div className="mt-6 p-4 bg-blue-50 border-2 border-blue-200 rounded-xl">
                  <label className="block text-sm font-semibold text-blue-800 mb-2">Commentaire</label>
                  <textarea
                    value={commentaire}
                    onChange={(e) => setCommentaire(e.target.value)}
                    className="w-full p-3 border border-blue-300 rounded-lg resize-vertical focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                    rows="3"
                    placeholder="Ajouter un commentaire manuel..."
                  />
                  <button
                    onClick={async () => {
                      if (!numero) return
                      setSavingComment(true)
                      try {
                        const res = await fetch(`${API_URL}/factures/${numero}`, {
                          method: 'PUT',
                          headers: {'Content-Type': 'application/json'},
                          body: JSON.stringify({commentaire})
                        })
                        if (res.ok) {
                          alert('Commentaire sauvegardé !')
                        } else {
                          alert('Erreur sauvegarde')
                        }
                      } catch (e) {
                        alert('Erreur réseau')
                      }
                      setSavingComment(false)
                    }}
                    disabled={!numero || savingComment}
                    className="mt-3 bg-blue-600 hover:bg-blue-700 text-white font-medium py-2 px-4 rounded-lg flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
                  >
                    <Save size={16} />
                    {savingComment ? 'Sauvegarde...' : 'Valider et sauvegarder'}
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* ── OCR ── */}
          {tab === 'ocr' && (
            <div className="bg-gray-50 border border-gray-200 rounded-lg p-4 max-h-96 overflow-auto font-mono text-xs leading-relaxed">
              {(result?.ocr_preview_lines || []).slice(0, 50).map((line, i) => (
                <div key={i} className="border-b border-gray-100 py-0.5 last:border-0">
                  <span className="text-gray-300 mr-3 select-none">{String(i+1).padStart(2,'0')}</span>
                  {line || <span className="text-gray-300">—</span>}
                </div>
              ))}
              {(result?.ocr_preview_lines?.length||0) > 50 &&
                <p className="text-gray-400 mt-3 text-center">+{result.ocr_preview_lines.length - 50} lignes...</p>}
            </div>
          )}

          {/* ── JSON ── */}
          {tab === 'json' && (
            <div>
              <div className="flex justify-end mb-3">
                <button onClick={() => navigator.clipboard.writeText(JSON.stringify(d, null, 2))}
                  className="btn-secondary text-xs py-1.5 px-3 flex items-center gap-1.5">
                  <Copy size={12}/> Copier
                </button>
              </div>
              <pre className="bg-gray-50 border border-gray-200 rounded-lg p-4 text-xs max-h-96 overflow-auto leading-relaxed">
                {JSON.stringify(d, null, 2)}
              </pre>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

// ── Page principale ───────────────────────────────────────────────────────────

export default function Factures({ lastResult, queue, setQueue, handleAddFiles, retryQueueItem }) {
  const [globalError, setGlobalError] = useState('')
  const [selectedResult, setSelectedResult] = useState(null)
  // showNewAnalysis : l'utilisateur a cliqué "Nouvelle analyse" — afficher la dropzone
  // sans effacer lastResult (pour qu'il reste accessible si on revient)
  const [showNewAnalysis, setShowNewAnalysis] = useState(false)

  // Affiche le résultat précédent uniquement si aucune queue active et pas en mode "nouvelle analyse"
  const showLastResult = lastResult && queue.length === 0 && !selectedResult && !showNewAnalysis

  const onFiles = (files) => {
    setGlobalError('')
    setShowNewAnalysis(false) // retour automatique dès qu'un fichier est ajouté
    handleAddFiles(files)
  }

  const removeFromQueue = (id) => {
    setQueue(prev => prev.filter(i => i.id !== id || i.status === 'processing'))
  }


  const isRunning  = queue.some(i => i.status === 'processing')
  const allDone    = queue.length > 0 && queue.every(i => i.status === 'done' || i.status === 'error')

  const statusIcon = (item) => {
    if (item.status === 'waiting')    return <Clock size={16} className="text-gray-400"/>
    if (item.status === 'processing') return <div className="w-4 h-4 border-2 border-blue-500 border-t-transparent rounded-full animate-spin"/>
    if (item.status === 'done')       return <CheckCircle size={16} className="text-green-500"/>
    if (item.status === 'error')      return <XCircle size={16} className="text-red-500"/>
    return null
  }

  const statusLabel = (item) => {
    if (item.status === 'waiting')    return <span className="text-xs text-gray-400">En attente</span>
    if (item.status === 'processing') return <span className="text-xs text-blue-600 font-medium">Analyse en cours...</span>
    if (item.status === 'error')      return <span className="text-xs text-red-600">{item.error}</span>
    if (item.status === 'done' && item.result) return <StatutPill statut={item.result.validation}/>
    return null
  }

  // Afficher le détail d'un résultat sélectionné
  if (selectedResult) {
    return (
      <div className="p-6 max-w-7xl mx-auto">
        <ResultView result={selectedResult} item={queue.find(i => i.result === selectedResult) || {}} onBack={() => setSelectedResult(null)}/>
      </div>
    )
  }

  // Afficher le dernier résultat unique (si aucune queue active)
  if (showLastResult) {
    const handleNewAnalysis = () => {
      // Conserver lastResult comme item virtuel dans la queue pour ne pas le perdre
      const d = lastResult?.data ?? lastResult
      setQueue(prev => [...prev, {
        id:      Date.now() + Math.random(),
        file:    null,
        virtual: true,
        label:   d?.prestataire ?? 'Facture précédente',
        sublabel: d?.numero_facture ?? '',
        status:  'done',
        result:  lastResult,
        error:   null,
      }])
      setShowNewAnalysis(true)
    }
    return (
      <div className="p-6 max-w-5xl mx-auto">
        <ResultView result={lastResult} onBack={handleNewAnalysis}/>
      </div>
    )
  }

  return (
    <div className="p-6 max-w-3xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Analyser des factures</h1>
        <p className="text-gray-500 text-sm mt-1">
          Déposez une ou plusieurs factures PDF — elles seront traitées automatiquement.
        </p>
      </div>

      {/* Zone de dépôt */}
      <MultiDropzone onFiles={onFiles} disabled={isRunning}/>

      {/* File d'attente */}
      {queue.length > 0 && (
        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
          <div className="flex items-center justify-between px-5 py-3 border-b border-gray-100 bg-gray-50">
            <div className="flex items-center gap-2">
              <h3 className="text-sm font-semibold text-gray-700">File de traitement</h3>
              <span className="text-xs bg-blue-100 text-blue-700 font-medium px-2 py-0.5 rounded-full">
                {queue.length} facture{queue.length > 1 ? 's' : ''}
              </span>
            </div>
          </div>

          <ul className="divide-y divide-gray-100">
            {queue.map(item => (
              <li key={item.id} className="flex items-center gap-4 px-5 py-4">
                {statusIcon(item)}
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-gray-800 truncate">
                    {item.virtual ? item.label : item.file.name}
                  </p>
                  <p className="text-xs text-gray-400">
                    {item.virtual ? item.sublabel : `${(item.file.size / 1024 / 1024).toFixed(2)} Mo`}
                  </p>
                </div>
                <div className="flex items-center gap-3">
                  {statusLabel(item)}
                  {item.status === 'done' && item.result && (
                    <button
                      onClick={() => setSelectedResult(item.result)}
                      className="text-xs text-blue-600 hover:underline font-medium"
                    >
                      Voir détails →
                    </button>
                  )}
                  {item.status === 'error' && (
                    <button
                      onClick={() => retryQueueItem(item.id)}
                      className="text-xs text-blue-600 hover:underline font-medium"
                    >
                      Réessayer
                    </button>
                  )}
                  {item.status === 'waiting' && !item.virtual && (
                    <button onClick={() => removeFromQueue(item.id)} className="text-gray-300 hover:text-gray-500">
                      <X size={14}/>
                    </button>
                  )}
                </div>
              </li>
            ))}
          </ul>

          {allDone && (
            <div className="px-5 py-3 border-t border-gray-100 bg-gray-50">
              <p className="text-sm text-gray-500">
                ✓ Traitement terminé —{' '}
                {queue.filter(i => i.status === 'done').length} réussie(s),{' '}
                {queue.filter(i => i.status === 'error').length} erreur(s)
              </p>
            </div>
          )}
        </div>
      )}

      {globalError && (
        <div className="bg-red-50 border border-red-200 rounded-lg px-4 py-3 text-red-700 text-sm flex items-start gap-2">
          <XCircle size={16} className="flex-shrink-0 mt-0.5"/>{globalError}
        </div>
      )}
    </div>
  )
}

// ── Dropzone multi-fichiers ───────────────────────────────────────────────────

function MultiDropzone({ onFiles, disabled }) {
  const inputRef = useRef(null)
  const [dragging, setDragging] = useState(false)

  const handle = (files) => {
    const pdfs = Array.from(files).filter(f => f.type === 'application/pdf')
    if (pdfs.length > 0) onFiles(pdfs)
  }

  return (
    <div
      onDragOver={e => { e.preventDefault(); setDragging(true) }}
      onDragLeave={() => setDragging(false)}
      onDrop={e => { e.preventDefault(); setDragging(false); if (!disabled) handle(e.dataTransfer.files) }}
      onClick={() => !disabled && inputRef.current?.click()}
      className={`border-2 border-dashed rounded-xl p-12 text-center cursor-pointer transition-colors
        ${dragging ? 'border-blue-500 bg-blue-50' : 'border-gray-300 hover:border-blue-400 hover:bg-gray-50'}
        ${disabled ? 'opacity-50 cursor-not-allowed' : ''}`}
    >
      <input
        ref={inputRef}
        type="file"
        accept="application/pdf"
        multiple
        className="hidden"
        onChange={e => handle(e.target.files)}
        disabled={disabled}
      />
      <div className="flex flex-col items-center gap-3">
        <Upload size={40} className={dragging ? 'text-blue-500' : 'text-gray-400'}/>
        <div>
          <p className="text-gray-700 font-medium">
            {dragging ? 'Déposez les fichiers ici' : 'Glissez vos factures ici'}
          </p>
          <p className="text-sm text-gray-400 mt-1">PDF uniquement — plusieurs fichiers acceptés</p>
        </div>
        <button type="button" className="btn-secondary text-sm mt-2" onClick={e => { e.stopPropagation(); inputRef.current?.click() }}>
          Parcourir
        </button>
      </div>
    </div>
  )
}

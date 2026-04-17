const pageMeta = {
  dashboard:    'Tableau de bord',
  factures:     'Analyser une facture',
  historique:   'Historique',
  fournisseurs: 'Fournisseurs',
}

export default function TopBar({ activePage }) {
  const today = new Date().toLocaleDateString('fr-FR', {
    weekday: 'long', day: 'numeric', month: 'long', year: 'numeric'
  })

  return (
    <header className="h-14 bg-white border-b border-gray-200 flex items-center justify-between px-6 flex-shrink-0 sticky top-0 z-10">
      <div>
        <h1 className="text-base font-semibold text-gray-900">{pageMeta[activePage] || ''}</h1>
        <p className="text-xs text-gray-400 capitalize">{today}</p>
      </div>
    </header>
  )
}

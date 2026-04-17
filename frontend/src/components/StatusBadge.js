const STATUS_CONFIG = {
  'accepté':               { label: 'Validée',      className: 'bg-green-100 text-green-700'   },
  'accepté_avec_réserve':  { label: 'Sous réserve', className: 'bg-yellow-100 text-yellow-800' },
  'rejeté':                { label: 'Rejetée',      className: 'bg-red-100 text-red-700'       },
}

export function StatusBadge({ status }) {
  const cfg = STATUS_CONFIG[status] ?? { label: status || '—', className: 'bg-gray-100 text-gray-600' }
  return (
    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${cfg.className}`}>
      {cfg.label}
    </span>
  )
}

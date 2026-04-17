import { Building2 } from 'lucide-react'

export default function Fournisseurs() {
  return (
    <div className="p-6 max-w-xl">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Fournisseurs</h1>
        <p className="text-gray-500 text-sm mt-1">Référentiel des prestataires</p>
      </div>

      <div className="card text-center py-16">
        <div className="w-16 h-16 bg-blue-100 rounded-full flex items-center justify-center mx-auto mb-4">
          <Building2 size={28} className="text-blue-600" />
        </div>
        <h2 className="text-lg font-semibold text-gray-900 mb-2">
          Module en cours de développement
        </h2>
        <p className="text-gray-500 text-sm leading-relaxed max-w-sm mx-auto">
          Cette section permettra de gérer le référentiel des fournisseurs agréés,
          leurs coordonnées bancaires et leur statut de validation.
        </p>
      </div>
    </div>
  )
}

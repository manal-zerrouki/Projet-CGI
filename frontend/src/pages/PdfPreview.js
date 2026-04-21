import { useState, useEffect } from 'react'

export default function PdfPreview({ file, className = 'w-full h-96' }) {
  const [url, setUrl] = useState(null)

  useEffect(() => {
    if (!file) {
      setUrl(null)
      return
    }

    const objectUrl = URL.createObjectURL(file)
    setUrl(objectUrl)

    return () => {
      URL.revokeObjectURL(objectUrl)
    }
  }, [file])

  if (!file || !url) {
    return (
      <div className={`${className} bg-gray-50 border-2 border-dashed border-gray-300 rounded-lg flex items-center justify-center`}>
        <span className="text-gray-400 text-lg font-medium">📄 PDF</span>
      </div>
    )
  }

  return (
    <iframe
      src={url}
      className={`${className} w-full h-full border rounded-lg shadow-lg`}
      title="Facture originale"
    />
  )
}


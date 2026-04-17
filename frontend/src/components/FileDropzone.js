import { useCallback } from 'react'
import { useDropzone } from 'react-dropzone'
import { Upload, FileText } from 'lucide-react'

export default function FileDropzone({ onFile, isLoading }) {
  const onDrop = useCallback((files) => {
    if (files[0]) onFile(files[0])
  }, [onFile])

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { 'application/pdf': ['.pdf'] },
    maxFiles: 1,
    disabled: isLoading,
  })

  return (
    <div
      {...getRootProps()}
      className={`border-2 border-dashed rounded-xl p-12 text-center cursor-pointer transition-colors
        ${isDragActive
          ? 'border-blue-500 bg-blue-50'
          : 'border-gray-300 hover:border-blue-400 hover:bg-gray-50'
        }
        ${isLoading ? 'opacity-50 cursor-not-allowed' : ''}`}
    >
      <input {...getInputProps()} />
      <div className="flex flex-col items-center gap-3">
        {isDragActive
          ? <Upload size={40} className="text-blue-500" />
          : <FileText size={40} className="text-gray-400" />
        }
        <div>
          <p className="text-gray-700 font-medium">
            {isDragActive ? 'Déposez le fichier ici' : 'Glissez votre facture ici'}
          </p>
          <p className="text-sm text-gray-400 mt-1">PDF uniquement — max 50 Mo</p>
        </div>
        <button type="button" className="btn-secondary text-sm mt-2">
          Parcourir
        </button>
      </div>
    </div>
  )
}

import React, { useState } from "react";
import "./App.css";

const API_URL = process.env.REACT_APP_API_URL || "http://127.0.0.1:8000";

function App() {
  const [file, setFile] = useState(null);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");

  const onSubmit = async (e) => {
    e.preventDefault();
    setError("");
    setResult(null);

    if (!file) {
      setError("Choisis un fichier PDF.");
      return;
    }

    const formData = new FormData();
    formData.append("file", file);

    setLoading(true);
    try {
      const res = await fetch(`${API_URL}/analyze`, {
        method: "POST",
        body: formData,
      });

      const data = await res.json().catch(() => null);

      if (!res.ok) {
        const msg = data?.detail || data?.message || `Erreur HTTP ${res.status}`;
        throw new Error(msg);
      }

      setResult(data);
    } catch (err) {
      setError(err.message || "Erreur inconnue");
    } finally {
      setLoading(false);
    }
  };

  const jsonToShow = result?.data ?? result;

  return (
    <div className="page">
      <div className="card">
        <h1 className="title">Analyse de facture</h1>
        <p className="subtitle">Upload PDF → OCR → Extraction JSON</p>

        <form onSubmit={onSubmit} className="form">
          <input
            type="file"
            accept="application/pdf"
            onChange={(e) => setFile(e.target.files?.[0] || null)}
          />

          <button className="btn" type="submit" disabled={loading}>
            {loading ? "Analyse en cours..." : "Analyser"}
          </button>
        </form>

        {error && <div className="error">{error}</div>}

        {result && (
          <div className="grid">
            <div className="block">
              <h2>Résultat JSON</h2>
              <pre className="pre">{JSON.stringify(jsonToShow, null, 2)}</pre>

              {Array.isArray(result?.data?.warnings) && result.data.warnings.length > 0 && (
                <div className="warnings">
                  <h3>Warnings</h3>
                  <ul>
                    {result.data.warnings.map((w, i) => (
                      <li key={i}>{w}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>

            <div className="block">
              <h2>Aperçu OCR</h2>
              <div className="ocr">
                {(result?.ocr_preview_lines || []).length === 0 ? (
                  <span className="muted">Aucun aperçu disponible</span>
                ) : (
                  result.ocr_preview_lines.map((line, idx) => (
                    <div key={idx} className="ocrLine">
                      {line || <span className="muted">(ligne vide)</span>}
                    </div>
                  ))
                )}
              </div>
            </div>
          </div>
        )}
      </div>

      <div className="footer">
        API: <code>{API_URL}</code>
      </div>
    </div>
  );
}

export default App;
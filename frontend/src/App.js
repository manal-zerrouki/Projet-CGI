import React, { useState, useEffect } from "react";
import "./App.css";

const API_URL = "http://127.0.0.1:8000"; // 🔥 FIX IMPORTANT

function App() {
  console.log("APP RENDER");
  const [file, setFile] = useState(null);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [factures, setFactures] = useState([]);

  const fetchFactures = () => {
    console.log("FETCH FACTURES START");
  
    fetch("http://127.0.0.1:8000/factures") // 🔥 FORCER URL
      .then(res => {
        console.log("STATUS:", res.status);
        return res.json();
      })
      .then(data => {
        console.log("DATA REACT:", data); // 🔥 IMPORTANT
        setFactures(Array.isArray(data) ? data : []);
      })
      .catch(err => console.error("FETCH ERROR:", err));
  };

  // ✅ Chargement initial
  useEffect(() => {
    console.log("USE EFFECT RUNNING");
    fetchFactures();
  }, []);

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

      // 🔥 refresh historique après analyse
      fetchFactures();

    } catch (err) {
      setError(err.message || "Erreur inconnue");
    } finally {
      setLoading(false);
    }
  };

  const data = result?.data ?? result;

  return (
    <div className="app">
      <header className="header">
        <div className="logo">
          <h1 style={{
            fontSize: '3.5rem',
            fontWeight: '900',
            background: 'linear-gradient(135deg, #6366f1, #8b5cf6, #ec4899)',
            WebkitBackgroundClip: 'text',
            WebkitTextFillColor: 'transparent',
            margin: 0
          }}>
            CGI
          </h1>
          <p style={{ color: '#64748b' }}>
            Analyse Intelligente de Factures
          </p>
        </div>
      </header>

      <div className="main">
        <div className="upload-section">
          <div className="upload-card">

            <h2>Upload ta facture</h2>

            <form onSubmit={onSubmit}>
              <input
                type="file"
                accept="application/pdf"
                onChange={(e) => setFile(e.target.files?.[0] || null)}
              />

              <button type="submit" disabled={!file || loading}>
                {loading ? "Analyse..." : "Analyser Facture"}
              </button>
            </form>

            {error && <p style={{ color: "red" }}>{error}</p>}
          </div>
        </div>

        {/* 🔥 HISTORIQUE */}
        <div style={{ marginTop: "60px" }}>
          <h2 style={{ textAlign: "center" }}>
            Historique des factures
          </h2>

          {/* DEBUG */}
          <p style={{ textAlign: "center" }}>
            {factures.length === 0
              ? "Aucune facture chargée"
              : `${factures.length} factures`}
          </p>

          <div style={{ overflowX: "auto", marginTop: "20px" }}>
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr style={{ background: "#f3f4f6" }}>
                  <th style={{ padding: "12px" }}>Numéro</th>
                  <th style={{ padding: "12px" }}>Prestataire</th>
                  <th style={{ padding: "12px" }}>Date</th>
                </tr>
              </thead>

              <tbody>
                {factures.map((f, i) => (
                  <tr key={i} style={{
                    textAlign: "center",
                    borderBottom: "1px solid #e5e7eb"
                  }}>
                    <td style={{ padding: "10px" }}>
                      {f.numero_facture}
                    </td>
                    <td style={{ padding: "10px" }}>
                      {f.prestataire}
                    </td>
                    <td style={{ padding: "10px" }}>
                      {f.date_creation
                        ? new Date(f.date_creation).toLocaleString()
                        : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

      </div>
    </div>
  );
}

export default App;
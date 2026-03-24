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

  const data = result?.data ?? result;

  const getTtcLettresCoherence = () => {
    if (!data?.montant_ttc_lettres) return 'Non renseigné';
    const hasIncoherence = result.motifs_rejet?.some(m => m.toLowerCase().includes('lettres'));
    const hasWarning = result.warnings?.some(w => w.toLowerCase().includes('lettres'));
    if (hasIncoherence) return '❌ Incohérente';
    if (hasWarning) return '⚠️ Non vérifiable automatiquement';
    return '✅ Cohérente avec TTC chiffres';
  };

  const FieldCard = ({label, value, type = 'text', highlight = false}) => {
    const isFilled = value != null && value !== '' && value !== false;
    const isAmount = type === 'amount';
    const isDate = type === 'date';
    let displayValue = value;

    if (isAmount && value != null) {
      displayValue = new Intl.NumberFormat('fr-FR', {style: 'currency', currency: data?.devise || 'EUR'}).format(value);
    } else if (isDate && value) {
      const [day, month, year] = value.split('-');
      displayValue = new Date(year, month - 1, day).toLocaleDateString('fr-FR');
    }

    const color = isFilled ? (highlight ? '#059669' : '#10b981') : '#6b7280';
    const bgColor = isFilled ? (highlight ? '#d1fae5' : '#ecfdf5') : '#f3f4f6';

    return (
      <div style={{
        padding: '16px 20px',
        borderRadius: '12px',
        border: `2px solid ${color}`,
        backgroundColor: bgColor,
        boxShadow: '0 2px 8px rgba(0,0,0,0.08)',
        display: 'flex',
        flexDirection: 'column',
        gap: '6px',
        transition: 'all 0.2s ease'
      }}
      onMouseEnter={(e) => e.currentTarget.style.transform = 'translateY(-2px)'}
      onMouseLeave={(e) => e.currentTarget.style.transform = 'translateY(0)'}
      >
        <div style={{fontSize: '11px', fontWeight: 600, color: '#4b5563', textTransform: 'uppercase', letterSpacing: '0.08em'}}>
          {label}
        </div>
        <div style={{
          fontSize: highlight ? '22px' : '20px',
          fontWeight: highlight ? '800' : '700',
          color,
          minHeight: '28px'
        }}>
          {displayValue != null ? displayValue : '—'}
        </div>
      </div>
    );
  };

  return (
    <div className="app">
      {/* Header CGI */}
      <header className="header">
        <div className="logo">
          <h1 style={{fontSize: '3.5rem', fontWeight: '900', background: 'linear-gradient(135deg, #6366f1, #8b5cf6, #ec4899)', 
                      WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent', margin: 0, lineHeight: 1}}>
            CGI
          </h1>
          <p style={{fontSize: '1.4rem', color: '#64748b', margin: '8px 0 0', fontWeight: 500}}>Analyse Intelligente de Factures</p>
        </div>
      </header>

      <div className="main">
        <div className="upload-section">
          <div className="upload-card">
            <div style={{textAlign: 'center', marginBottom: '32px'}}>
              <div style={{fontSize: '4rem', marginBottom: '16px'}}>📄</div>
              <h2 style={{fontSize: '2rem', color: '#1f2937', marginBottom: '8px'}}>Upload ta facture</h2>
              <p style={{color: '#6b7280', fontSize: '1.1rem'}}>PDF scanné → OCR Tesseract → LLM extraction → Cases automatiques</p>
            </div>

            <form onSubmit={onSubmit} style={{display: 'flex', flexDirection: 'column', gap: '20px', maxWidth: '500px', margin: '0 auto'}}>
              <div style={{position: 'relative'}}>
                <input
                  id="file-upload"
                  type="file"
                  accept="application/pdf"
                  onChange={(e) => setFile(e.target.files?.[0] || null)}
                  style={{
                    width: '100%',
                    padding: '20px',
                    border: '3px dashed #d1d5db',
                    borderRadius: '16px',
                    background: '#f8fafc',
                    cursor: 'pointer',
                    fontSize: '16px'
                  }}
                />
                {file && (
                  <div style={{position: 'absolute', top: 8, right: 12, background: '#10b981', color: 'white', padding: '4px 12px', borderRadius: '20px', fontSize: '12px', fontWeight: 600}}>
                    ✓ Prêt
                  </div>
                )}
              </div>

              <button 
                className="upload-btn" 
                type="submit" 
                disabled={!file || loading}
                style={{
                  padding: '20px 40px',
                  fontSize: '1.2rem',
                  fontWeight: 700,
                  borderRadius: '16px',
                  border: 'none',
                  background: 'linear-gradient(135deg, #6366f1 0%, #8b5cf6 50%, #ec4899 100%)',
                  color: 'white',
                  cursor: file && !loading ? 'pointer' : 'not-allowed',
                  opacity: file && !loading ? 1 : 0.7,
                  boxShadow: '0 10px 25px rgba(99, 102, 241, 0.4)',
                  transition: 'all 0.3s ease'
                }}
              >
                {loading ? (
                  <>
                    <span style={{marginRight: '12px'}}>⚡</span>
                    Analyse en cours...
                  </>
                ) : (
                  <>
                    <span style={{marginRight: '12px'}}>🚀</span>
                    Analyser Facture
                  </>
                )}
              </button>
            </form>

            {error && (
              <div style={{
                marginTop: '24px',
                padding: '20px',
                borderRadius: '12px',
                background: 'linear-gradient(135deg, #fee2e2, #fecaca)',
                borderLeft: '5px solid #ef4444',
                color: '#991b1b'
              }}>
                {error}
              </div>
            )}
          </div>
        </div>

        {result && (
          <div style={{marginTop: '60px'}}>
            {/* Reste du code résultat identique */}
            <div style={{maxWidth: '1400px', margin: '0 auto'}}>
              <div style={{marginBottom: '40px', textAlign: 'center'}}>
                <h2 style={{fontSize: '2.5rem', background: 'linear-gradient(135deg, #10b981, #059669)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent', margin: 0}}>
                  Résultats Extraction
                </h2>
              </div>

              {/* Validation Status */}
              <div style={{textAlign: 'center', marginBottom: '40px'}}>
                <div style={{
                  display: 'inline-block',
                  padding: '16px 48px',
                  borderRadius: '20px',
                  fontSize: '1.5rem',
                  fontWeight: 800,
                  color: result.validation === 'accepté' ? '#059669' : result.validation === 'accepté_avec_réserve' ? '#d97706' : '#dc2626',
                  background: result.validation === 'accepté' ? 'linear-gradient(135deg, #d1fae5, #a7f3d0)' :
                              result.validation === 'accepté_avec_réserve' ? 'linear-gradient(135deg, #fef3c7, #fde68a)' :
                              'linear-gradient(135deg, #fee2e2, #fecaca)'
                }}>
                  {result.validation?.toUpperCase() || 'TRAITEMENT'}
                </div>

                {result.motifs_rejet?.length > 0 && (
                  <div style={{marginTop: '24px', textAlign: 'left', maxWidth: '800px', margin: '24px auto 0'}}>
                    <div style={{fontSize: '1rem', fontWeight: 700, color: '#dc2626', marginBottom: '12px'}}>
                      🚫 Motifs de rejet
                    </div>
                    <ul style={{listStyle: 'none', padding: 0, margin: 0, display: 'flex', flexDirection: 'column', gap: '8px'}}>
                      {result.motifs_rejet.map((motif, i) => (
                        <li key={i} style={{
                          display: 'flex', alignItems: 'flex-start', gap: '10px',
                          padding: '12px 16px', borderRadius: '10px',
                          background: '#fff5f5', border: '1px solid #fecaca', color: '#991b1b', fontSize: '0.95rem'
                        }}>
                          <span style={{flexShrink: 0}}>❌</span>
                          <span>{motif}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>

              {/* Main Grid */}
              <div style={{display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(400px, 1fr))', gap: '32px'}}>
                <div style={{background: 'white', padding: '32px', borderRadius: '24px', boxShadow: '0 20px 60px rgba(0,0,0,0.1)'}}>
                  <h3 style={{fontSize: '1.5rem', color: '#1f2937', marginBottom: '24px', display: 'flex', alignItems: 'center', gap: '12px'}}>
                    📋 INFORMATIONS PRINCIPALES
                  </h3>
                  <div style={{display: 'grid', gap: '20px'}}>
                    <FieldCard label="Prestataire" value={data.prestataire} />
                    <FieldCard label="ICE" value={data.ice} />
                    <FieldCard label="N° Facture" value={data.numero_facture} />
                    <FieldCard label="Date Facture" value={data.date_facture} type="date" />
                    <FieldCard label="Échéance" value={data.date_echeance} type="date" />
                    <FieldCard label="N° Engagement" value={data.numero_engagement} />
                    <FieldCard label="Cachet/Signature" value={
                      data.cachet_signature === true  ? '✅ Présent' :
                      data.cachet_signature === false ? '❌ Absent' :
                                                        '⚠️ Non détecté'
                    } />
                  </div>
                </div>

                <div style={{background: 'white', padding: '32px', borderRadius: '24px', boxShadow: '0 20px 60px rgba(0,0,0,0.1)'}}>
                  <h3 style={{fontSize: '1.5rem', color: '#1f2937', marginBottom: '24px', display: 'flex', alignItems: 'center', gap: '12px'}}>
                    💰 MONTANTS
                  </h3>
                  <div style={{display: 'grid', gap: '20px'}}>
                    <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px'}}>
                      <FieldCard label="HT" value={data.montant_ht} type="amount" />
                      <FieldCard label="TVA" value={data.tva} type="amount" />
                    </div>
                    <FieldCard label="Taux TVA" value={data.taux_tva ? `${data.taux_tva}%` : null} />
                    <FieldCard label="TTC" value={data.montant_ttc} type="amount" highlight />
                    <FieldCard label="TTC Lettres" value={data.montant_ttc_lettres} />
                    <FieldCard label="Cohérence TTC Lettres / Chiffres" value={getTtcLettresCoherence()} />
                    <FieldCard label="Retenue Source" value={data.retenue_source} type="amount" />
                    <FieldCard label="NET À PAYER" value={data.net_a_payer} type="amount" highlight />
                    <FieldCard label="Devise" value={data.devise} />
                  </div>
                </div>
              </div>

              {/* Warnings & JSON */}
              {(data.warnings?.length > 0 || result.warnings?.length > 0 || result.exceptions?.length > 0) && (
                <div style={{marginTop: '40px', background: 'white', padding: '32px', borderRadius: '24px', boxShadow: '0 20px 60px rgba(0,0,0,0.1)'}}>
                  <h3 style={{fontSize: '1.5rem', color: '#f59e0b', marginBottom: '24px', display: 'flex', alignItems: 'center', gap: '12px'}}>
                    ⚠️ ALERTES & DÉTAILS
                  </h3>
                  <ul style={{margin: '0', paddingLeft: '24px', fontSize: '1.1rem'}}>
                    {result.warnings?.map((w, i) => (
                      <li key={`rw${i}`} style={{color: '#f59e0b', marginBottom: '8px'}}>{w}</li>
                    ))}
                    {data.warnings?.map((w, i) => (
                      <li key={`w${i}`} style={{color: '#f59e0b', marginBottom: '8px'}}>{w}</li>
                    ))}
                    {result.exceptions?.map((e, i) => (
                      <li key={`e${i}`} style={{color: '#d97706', marginBottom: '8px'}}>{e}</li>
                    ))}
                  </ul>
                </div>
              )}

              <div style={{marginTop: '40px', display: 'grid', gridTemplateColumns: '2fr 1fr', gap: '32px'}}>
                <div style={{background: 'white', padding: '32px', borderRadius: '24px', boxShadow: '0 20px 60px rgba(0,0,0,0.1)'}}>
                  <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px'}}>
                    <h3 style={{fontSize: '1.5rem', color: '#1f2937', margin: 0}}>📄 JSON Complet</h3>
                    <button 
                      onClick={() => navigator.clipboard.writeText(JSON.stringify(data, null, 2))}
                      style={{
                        padding: '12px 24px', 
                        borderRadius: '12px', 
                        border: '1px solid #d1d5db', 
                        background: 'white', 
                        cursor: 'pointer',
                        fontWeight: 600,
                        color: '#374151'
                      }}
                    >
                      📋 Copier JSON
                    </button>
                  </div>
                  <pre style={{margin: 0, background: '#f8fafc', padding: '24px', borderRadius: '12px', fontSize: '0.9rem', maxHeight: '400px', overflow: 'auto'}}>
                    {JSON.stringify(data, null, 2)}
                  </pre>
                </div>

                <div style={{background: 'white', padding: '32px', borderRadius: '24px', boxShadow: '0 20px 60px rgba(0,0,0,0.1)'}}>
                  <h3 style={{fontSize: '1.5rem', color: '#1f2937', marginBottom: '24px'}}>👁️ Aperçu OCR</h3>
                  <div style={{maxHeight: '400px', overflow: 'auto', background: '#f8fafc', padding: '20px', borderRadius: '12px', fontSize: '0.85rem', fontFamily: 'monospace', lineHeight: '1.4'}}>
                    {(result?.ocr_preview_lines || []).slice(0, 30).map((line, idx) => (
                      <div key={idx} style={{padding: '2px 0', borderBottom: '1px solid #e5e7eb'}}>
                        {line || <span style={{color: '#9ca3af'}}>—</span>}
                      </div>
                    ))}
                    {result.ocr_preview_lines?.length > 30 && <div style={{color: '#9ca3af', fontSize: '0.8rem'}}>... +{result.ocr_preview_lines.length - 30} lignes</div>}
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>

      <style>{`
        .app {
          min-height: 100vh;
          background: linear-gradient(135deg, #f8fafc 0%, #e2e8f0 100%);
          font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
        }
        .header {
          background: linear-gradient(135deg, #1e3a8a 0%, #3730a3 50%, #7c3aed 100%);
          color: white;
          padding: 40px 20px;
          text-align: center;
        }
        .logo {
          max-width: 1200px;
          margin: 0 auto;
        }
        .main {
          max-width: 1400px;
          margin: 0 auto;
          padding: 40px 20px;
        }
        .upload-section {
          margin-bottom: 60px;
        }
        .upload-card {
          background: white;
          padding: 60px 40px;
          border-radius: 32px;
          box-shadow: 0 25px 80px rgba(0,0,0,0.15);
          backdrop-filter: blur(20px);
          border: 1px solid rgba(255,255,255,0.2);
        }
        .upload-btn:hover {
          transform: translateY(-4px);
          box-shadow: 0 20px 40px rgba(99,102,241,0.5);
        }
      `}</style>
    </div>
  );
}

export default App;

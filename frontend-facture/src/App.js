import React, { useState } from 'react';
import axios from 'axios';
import './App.css';

function App() {
  const [file, setFile] = useState(null);
  const [result, setResult] = useState(null);
  const [errorMsg, setErrorMsg] = useState(''); // Pour stocker le message d'exception
  const [loading, setLoading] = useState(false);

  const handleSubmit = async () => {
    if (!file) return alert("Veuillez sélectionner un fichier.");
    
    setLoading(true);
    setResult(null);
    setErrorMsg(''); // On efface les anciennes erreurs

    const formData = new FormData();
    formData.append('file', file);

    try {
      const url = "http://localhost/backend-facture/process.php";
      const response = await axios.post(url, formData);

      if (response.data.status === 'success') {
        setResult(response.data.data);
      } else {
        // C'est ici qu'on récupère l'exception renvoyée par PHP
        setErrorMsg(response.data.message);
      }

    } catch (err) {
      console.error(err);
      setErrorMsg("Erreur critique de communication avec le serveur.");
    }
    setLoading(false);
  };

  return (
    <div className="container">
      <h1>Scanner de Facture IA</h1>
      
      <div className="card">
        <input type="file" onChange={(e) => setFile(e.target.files[0])} />
        <br/><br/>
        <button onClick={handleSubmit} disabled={loading}>
          {loading ? "Traitement en cours..." : "Lancer l'analyse"}
        </button>
      </div>

      {/* Affichage du Résultat (Succès) */}
      {result && (
        <div className="result-box success">
          <h3>✅ Données extraites :</h3>
          <p>🏢 <b>Prestataire :</b> {result.prestataire}</p>
          <p>📅 <b>Date :</b> {result.date_facture}</p>
          <p>🔢 <b>N° Facture :</b> {result.numero_facture}</p>
          <p>📝 <b>N° Engagement :</b> {result.numero_engagement}</p>
          <p>💰 <b>Montant :</b> {result.montant}</p>
        </div>
      )}

      {/* Affichage de l'Erreur (Exception) */}
      {errorMsg && (
        <div className="result-box error">
          <h3>❌ Erreur détectée :</h3>
          <p>{errorMsg}</p>
          <small>Cet incident a été enregistré dans la base de données.</small>
        </div>
      )}
    </div>
  );
}

export default App;
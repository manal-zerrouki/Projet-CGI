<?php
// ------------------------------------------------------------------
// CONFIGURATION DES HEADERS (CORS)
// ------------------------------------------------------------------
header("Access-Control-Allow-Origin: *");
header("Access-Control-Allow-Headers: Content-Type");
header("Access-Control-Allow-Methods: POST");
header("Content-Type: application/json");

// On inclut la connexion à la base de données
require 'db.php';

// Fonction utilitaire pour nettoyer le JSON renvoyé par l'IA
// (L'IA ajoute souvent des ```json au début et à la fin, il faut les enlever)
function cleanJson($text) {
    $text = str_replace(['```json', '```', 'json'], '', $text);
    $start = strpos($text, '{');
    $end = strrpos($text, '}');
    
    if ($start !== false && $end !== false) {
        return substr($text, $start, $end - $start + 1);
    }
    return $text; // Retourne le texte tel quel si pas d'accolades trouvées
}

// ------------------------------------------------------------------
// TRAITEMENT DU FICHIER
// ------------------------------------------------------------------
if ($_SERVER['REQUEST_METHOD'] === 'POST' && isset($_FILES['file'])) {
    
    // Création du dossier uploads s'il n'existe pas
    $uploadDir = 'uploads/';
    if (!is_dir($uploadDir)) mkdir($uploadDir, 0777, true);
    
    // Nom unique pour éviter d'écraser les fichiers
    $fileName = uniqid() . '_' . basename($_FILES['file']['name']);
    $uploadFile = $uploadDir . $fileName;

    // Déplacement du fichier temporaire vers le dossier final
    if (move_uploaded_file($_FILES['file']['tmp_name'], $uploadFile)) {
        try {
            // 1. PRÉPARATION DE L'IMAGE (Encodage Base64)
            // On transforme l'image en texte codé pour l'envoyer à l'API
            $imageData = base64_encode(file_get_contents($uploadFile));
            $mimeType = mime_content_type($uploadFile); // ex: image/jpeg, image/png

            // 2. CONFIGURATION DE L'API GEMINI
            $apiKey = "AIzaSyBflcacHzuoz7KkPfYJnHH75s7XBIaepoo"; 
            
            // On utilise le modèle LATEST (Rapide + Quota gratuit élevé)
            $url = "[https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent?key=](https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent?key=)" . $apiKey;

            // 3. LE PROMPT (L'ordre donné à l'IA)
            // On lui demande d'agir comme un moteur OCR intelligent + Extracteur
            $prompt = "Tu es un assistant comptable expert. Analyse cette image de facture.
            Ta mission :
            1. Lire tout le texte visible (OCR).
            2. Comprendre la structure (en-tête, totaux).
            3. Extraire les données ci-dessous au format JSON STRICT.
            
            Champs requis :
            - prestataire : Nom de la société qui a émis la facture.
            - date_facture : La date au format YYYY-MM-DD (ex: 2023-12-25).
            - numero_facture : Le numéro unique de la facture.
            - numero_engagement : Cherche 'Bon de commande', 'BC', 'Engagement', ou 'Réf Client'. Sinon null.
            - montant : Le montant TOTAL TTC (Net à payer). Juste le chiffre (ex: 1500.00).

            Si une info est introuvable, mets null. Ne réponds RIEN d'autre que le JSON.";

            // Construction du corps de la requête
            $data = [
                "contents" => [
                    [
                        "parts" => [
                            ["text" => $prompt],
                            [
                                "inline_data" => [
                                    "mime_type" => $mimeType,
                                    "data" => $imageData
                                ]
                            ]
                        ]
                    ]
                ]
            ];

            // 4. ENVOI À GOOGLE (Via cURL)
            $ch = curl_init($url);
            curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
            curl_setopt($ch, CURLOPT_POST, true);
            curl_setopt($ch, CURLOPT_POSTFIELDS, json_encode($data));
            curl_setopt($ch, CURLOPT_HTTPHEADER, ['Content-Type: application/json']);
            curl_setopt($ch, CURLOPT_SSL_VERIFYPEER, false); // Fix pour XAMPP Local
            
            $response = curl_exec($ch);
            
            if (curl_errno($ch)) {
                throw new Exception('Erreur de connexion cURL : ' . curl_error($ch));
            }
            curl_close($ch);

            // 5. ANALYSE DE LA RÉPONSE
            $jsonResponse = json_decode($response, true);

            // Vérification si Google a renvoyé une erreur (ex: clé invalide, quota...)
            if (isset($jsonResponse['error'])) {
                throw new Exception("Erreur API Gemini : " . $jsonResponse['error']['message']);
            }

            // Récupération du texte généré
            $rawText = $jsonResponse['candidates'][0]['content']['parts'][0]['text'] ?? null;

            if (!$rawText) {
                throw new Exception("L'IA n'a renvoyé aucun texte. Image illisible ?");
            }

            // Nettoyage du JSON (retirer les ```json)
            $cleanText = cleanJson($rawText);
            $factureData = json_decode($cleanText, true);

            // Vérification finale du format JSON
            if (json_last_error() !== JSON_ERROR_NONE) {
                // On garde un bout du texte pour comprendre l'erreur
                throw new Exception("L'IA n'a pas renvoyé un JSON valide. Réponse reçue : " . substr($cleanText, 0, 50) . "...");
            }

            // 6. SUCCÈS : ENREGISTREMENT EN BASE DE DONNÉES
            $stmt = $pdo->prepare("INSERT INTO factures (prestataire, date_facture, numero_facture, numero_engagement, montant, fichier_source, exception) VALUES (?, ?, ?, ?, ?, ?, NULL)");
            
            $stmt->execute([
                $factureData['prestataire'] ?? null,
                $factureData['date_facture'] ?? null,
                $factureData['numero_facture'] ?? null,
                $factureData['numero_engagement'] ?? null,
                $factureData['montant'] ?? null,
                $fileName
            ]);

            // Renvoi des données au Frontend (React)
            echo json_encode(["status" => "success", "data" => $factureData]);

        } catch (Exception $e) {
            // 7. EN CAS D'ERREUR (Exception)
            // On insère l'erreur dans la base de données pour garder une trace
            try {
                $stmtError = $pdo->prepare("INSERT INTO factures (fichier_source, exception) VALUES (?, ?)");
                $stmtError->execute([$fileName, $e->getMessage()]);
            } catch (Exception $dbError) {
                // Si la base de données est éteinte, on ne peut rien faire ici
            }

            // On renvoie l'erreur au Frontend pour l'afficher en rouge
            echo json_encode(["status" => "error", "message" => $e->getMessage()]);
        }
    } else {
        echo json_encode(["status" => "error", "message" => "Échec du téléchargement du fichier sur le serveur."]);
    }
}
?>
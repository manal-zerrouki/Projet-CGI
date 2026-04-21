# Modifications factures

✅ 0. Plan approuvé - image preview + commentaire + règle date 60j → warning

✅ 1. Créer backend/create_db.sql (ALTER ADD commentaire)
✅ 2. Modifier backend/app/services/validation_service.py (60j → warning)
✅ 3. Ajouter backend/app/routes/invoice.py (PUT /factures/{id}/comment)
✅ 4. Modifier frontend/src/pages/Factures.js (propag preview/comment)
✅ 5. Update db_service.py SELECT
✅ 6. Installer pdfjs frontend (npm)
✅ Modifications terminées !

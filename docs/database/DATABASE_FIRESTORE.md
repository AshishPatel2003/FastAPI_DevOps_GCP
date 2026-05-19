# GCP Firestore Reference

To use native GCP NoSQL:

1. Run `scripts/database/setup-firestore.sh`.
2. Add `google-cloud-firestore` to `requirements.txt`.
3. In `app/crud/`, replace SQLAlchemy sessions with `AsyncClient`:
   ```python
   from google.cloud.firestore import AsyncClient
   db = AsyncClient(project=settings.GCP_PROJECT_ID)
   doc = await db.collection("users").document(user_id).get()
   ```
4. Remove Alembic migrations (schema-less).

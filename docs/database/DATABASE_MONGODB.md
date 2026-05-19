# MongoDB Atlas Reference

To use MongoDB instead of SQL:

1. Create a free Atlas M0 cluster.
2. Use `scripts/database/setup-mongodb.sh` as a guide.
3. Replace SQLAlchemy/Alembic in `requirements.txt` with `motor` (async driver) and `beanie` (async ODM).
4. Remove `app/db/session.py` and `alembic/`.
5. In `app/main.py` lifespan, initialize Beanie:
   ```python
   client = AsyncIOMotorClient(settings.MONGODB_URL)
   await init_beanie(database=client.fastapi_db, document_models=[User])
   ```

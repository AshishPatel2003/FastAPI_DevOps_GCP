# MySQL Cloud SQL Reference

If you choose to use MySQL instead of PostgreSQL:

1. Use `scripts/database/setup-mysql.sh` to provision the instance.
2. In `requirements.txt`, replace `asyncpg` with `aiomysql`.
3. In `app/db/session.py`, the URL format changes slightly but the unix socket proxy logic remains exactly the same.
4. Set GitHub Secret `DATABASE_URL: mysql+aiomysql://user:pass@localhost:3306/db`

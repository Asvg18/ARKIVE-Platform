Reserved for database assets that aren't Python code — ERD exports, raw SQL
snapshots, data dictionaries, etc.

Migrations live in `backend/alembic/` and the demo-user seed script lives in
`backend/scripts/seed_demo_users.py`, both co-located with the app because
they import its SQLAlchemy models directly.

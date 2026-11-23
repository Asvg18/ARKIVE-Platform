#!/bin/sh
# Applies any pending schema migrations, then starts the API.
#
# Run here rather than as a separate compose service so the schema can
# never be a step someone forgets: 21 migrations exist, and a container
# started against an un-migrated database fails with confusing "relation
# does not exist" errors rather than anything that points at the cause.
set -e

echo "==> applying database migrations"
alembic upgrade head

echo "==> starting API"
# --forwarded-allow-ips is what lets the rate limiters see the real
# visitor instead of the proxy.
#
# Caddy sits in front of this container, so without it every request
# arrives claiming to come from Caddy's address and `request.client.host`
# is the same string for every human being on earth. Two live effects,
# both invisible in development because nothing fronts uvicorn there:
# the signup cap (per visitor, per hour) silently becomes a cap for the
# whole system, and the login lockout -- keyed on email *and* address
# precisely so nobody can lock out a known user on purpose -- loses the
# address half and becomes exactly that.
#
# Never "*". That makes uvicorn trust the *first* entry in
# X-Forwarded-For, which is the one a caller can type; an attacker would
# then get a fresh identity per request and no limit would apply at all.
# Naming the proxy's network instead means uvicorn walks the list from
# the right and takes the first address outside it -- the real client,
# whatever the caller prepended.
exec python -m uvicorn app.main:app \
	--host 0.0.0.0 \
	--port 8000 \
	--forwarded-allow-ips "${FORWARDED_ALLOW_IPS:-127.0.0.1}"

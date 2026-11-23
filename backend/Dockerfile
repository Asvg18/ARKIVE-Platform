# Backend image for the on-premises deployment. Pinned to the same
# Python the venv runs (3.12) so a dependency that resolves locally
# cannot resolve differently in the container.
FROM python:3.12-slim

# psycopg is installed as psycopg-binary (see requirements.txt), so no
# libpq build step is needed here. curl is for the healthcheck below.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Requirements copied and installed before the source, so an edit to the
# app does not invalidate the (slow) dependency layer.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Uploaded resumes and documents live here. Bind this to a volume in
# compose — without one, every container rebuild would silently destroy
# real applicant files.
RUN mkdir -p /app/uploads

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=5s --start-period=60s --retries=5 \
    CMD curl -fsS http://localhost:8000/public/jobs > /dev/null || exit 1

# The entrypoint runs `alembic upgrade head` first — see the script for
# why that is not a separate compose service. No --reload: that is a
# dev-server flag and doubles memory for no benefit. Bound to 0.0.0.0
# because the container's loopback is not reachable from the proxy.
CMD ["./docker-entrypoint.sh"]

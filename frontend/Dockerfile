# Build-only image: the output is a directory of static files that Caddy
# serves. Nothing from this stage runs in production, so node never
# reaches the deployed machine.
FROM node:22-slim AS build

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm ci

COPY . .

# Relative, not an absolute host — the proxy serves the app and the API
# from the same origin, so the browser never makes a cross-origin
# request and CORS stops being involved at all.
ENV VITE_API_BASE_URL=/api
RUN npm run build

# The runtime stage is just somewhere to copy `dist` out of.
FROM busybox:stable
COPY --from=build /app/dist /dist

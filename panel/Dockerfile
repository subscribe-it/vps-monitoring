# syntax=docker/dockerfile:1

# --- etap 1: build statycznej strony -----------------------------------------
FROM node:24-alpine AS build

WORKDIR /app

# pnpm instalowany przez npm (a nie corepack) — deterministyczna wersja bez
# zależności od kluczy podpisu corepack w obrazie bazowym.
RUN npm install --global pnpm@10.33.0

COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

COPY . .
RUN pnpm build

# --- etap 2: serwowanie ------------------------------------------------------
FROM nginx:alpine AS runtime

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

# Normalizacja uprawnień: pliki skopiowane z kontekstu budowania (np. public/)
# zachowują prawa z hosta. Gdyby któreś było czytelne tylko dla roota, nginx
# (proces `nginx`) zwróciłby 403 na istniejącym pliku.
RUN chmod -R a+rX /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD wget --quiet --spider http://127.0.0.1/healthz || exit 1

CMD ["nginx", "-g", "daemon off;"]

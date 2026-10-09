FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build && node scripts/prepare-runtime.mjs

FROM nginx:stable-alpine
ENV PORT=8080 \
    FRONTEND_BASE_URL=https://carte.fede.fpms.ac.be \
    NGINX_ENVSUBST_FILTER=^PORT$
COPY nginx/default.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html
COPY --from=build /app/runtime-templates /opt/frontend-templates
COPY --chmod=755 nginx/40-runtime-url.sh /docker-entrypoint.d/40-runtime-url.sh
EXPOSE 8080

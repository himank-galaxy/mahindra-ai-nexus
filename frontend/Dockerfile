# The checked-in frontend artifact is a Cloudflare Worker bundle. Wrangler is
# its supported local runtime; the Node proxy keeps the established :5174 URL
# and forwards /api and /health requests to the backend container.
FROM node:22-bookworm-slim

WORKDIR /app

RUN npm install --global wrangler@4.124.0

COPY .output ./.output
COPY vm-proxy.mjs ./vm-proxy.mjs
COPY docker-entrypoint.sh ./docker-entrypoint.sh

RUN chmod 0555 ./docker-entrypoint.sh

ENV FRONTEND_HOST=127.0.0.1 \
    FRONTEND_PORT=5175 \
    API_HOST=backend \
    API_PORT=8000

EXPOSE 5174

ENTRYPOINT ["./docker-entrypoint.sh"]

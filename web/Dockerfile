# syntax=docker/dockerfile:1
FROM node:20-alpine
WORKDIR /app

# Next.js bakes rewrite() destinations at BUILD time, so the /api proxy target must be set
# before `npm run build`. Defaults to the compose service name; override with --build-arg.
ARG API_REWRITE_TARGET=http://api:8000
ENV API_REWRITE_TARGET=$API_REWRITE_TARGET

COPY package.json package-lock.json* ./
RUN npm ci
COPY . .
RUN npm run build

ENV NODE_ENV=production
# Run as the image's built-in unprivileged user.
RUN chown -R node:node /app
USER node
EXPOSE 3000
CMD ["npm", "run", "start"]

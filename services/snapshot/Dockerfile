# Build context: services/snapshot. The image tag must match the playwright version in package.json.
FROM mcr.microsoft.com/playwright:v1.65.1-noble
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --omit=dev
COPY src src
ENV STITCHCRAFT_WEB_URL=http://web:8080 STITCHCRAFT_SNAPSHOT_PORT=8770 NODE_ENV=production
EXPOSE 8770
USER pwuser
CMD ["node", "src/server.mjs"]

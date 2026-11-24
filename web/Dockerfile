# Build context: repository root (the samples come from tests/reference)
FROM node:26-alpine AS build
RUN npm install -g pnpm@12.5.1
WORKDIR /src/web
COPY web/package.json web/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY web ./
COPY tests/reference /src/tests/reference
COPY data/render.json /src/data/render.json
RUN pnpm build

FROM nginx:1.29-alpine
COPY web/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /src/web/dist /usr/share/nginx/html
EXPOSE 8080

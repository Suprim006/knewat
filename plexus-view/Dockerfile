# Static build of the Plexus View behind nginx. Build context: ./plexus-view
#   docker build --build-arg VITE_PLEXUS_API=http://127.0.0.1:8080 -t plexus-view ./plexus-view
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
# The address the browser uses for the View API (baked into the bundle at build time).
ARG VITE_PLEXUS_API=http://127.0.0.1:8080
ENV VITE_PLEXUS_API=$VITE_PLEXUS_API
# Always the live API in the image: process env beats any .env file in Vite, so fixtures can't be baked in by accident.
ENV VITE_FIXTURES=0
RUN npx vite build

FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80

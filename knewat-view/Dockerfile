# Static build of the Knewat View behind nginx. Build context: ./knewat-view
#   docker build --build-arg VITE_KNEWAT_API=http://127.0.0.1:8080 -t knewat-view ./knewat-view
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
# The address the browser uses for the View API (baked into the bundle at build time).
ARG VITE_KNEWAT_API=http://127.0.0.1:8080
ENV VITE_KNEWAT_API=$VITE_KNEWAT_API
# Always the live API in the image: process env beats any .env file in Vite, so fixtures can't be baked in by accident.
ENV VITE_FIXTURES=0
RUN npx vite build

FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80

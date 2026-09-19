FROM node:22-alpine AS build
WORKDIR /app
# Copy the lockfile and use `npm ci` so the image is reproducible. Building from
# package.json alone re-resolved every caret range on each build.
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
ARG VITE_API_BASE=/api
ENV VITE_API_BASE=${VITE_API_BASE}
RUN npm run build

FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 8080

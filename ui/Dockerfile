# Stage 1: Build React App bằng Node
FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
RUN npm run build

# Stage 2: Serve bằng Nginx
FROM nginx:alpine
# Copy các file đã build từ Stage 1 vào thư mục của Nginx
COPY --from=builder /app/dist /usr/share/nginx/html
# Mở cổng 80 (cổng web mặc định)
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
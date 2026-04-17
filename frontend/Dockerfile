# 前端构建阶段
FROM node:20-alpine AS builder

WORKDIR /app

ARG VITE_API_BASE_URL=/api
ARG VITE_API_KEY
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
ENV VITE_API_KEY=${VITE_API_KEY}

# 复制 package 文件
COPY package*.json ./

# 安装依赖
RUN npm ci

# 复制源码
COPY . .

# 明确要求在构建阶段注入浏览器侧 API Key，避免生成不可用产物
RUN test -n "$VITE_API_KEY" || (echo "VITE_API_KEY build arg is required for frontend build" && exit 1)

# 构建生产版本
RUN npm run build

# 生产阶段 - 使用 Nginx 提供服务
FROM nginx:alpine

ARG VITE_API_KEY

# 复制构建产物到 Nginx 目录
COPY --from=builder /app/dist /usr/share/nginx/html

# 复制 Nginx 配置
COPY nginx.conf /etc/nginx/conf.d/default.conf

RUN test -n "$VITE_API_KEY" || (echo "VITE_API_KEY build arg is required for frontend nginx proxy config" && exit 1) && \
    sed -i "s|__FRONTEND_API_KEY__|${VITE_API_KEY}|g" /etc/nginx/conf.d/default.conf

# 创建非 root 用户并调整权限（使用 8080 端口以支持非特权运行）
RUN adduser -D -u 1001 appuser && \
    chown -R appuser:appuser /usr/share/nginx/html && \
    chown appuser:appuser /etc/nginx/conf.d/default.conf && \
    chown appuser:appuser /var/cache/nginx && \
    chown appuser:appuser /var/run

USER appuser

# 暴露端口
EXPOSE 8080

CMD ["nginx", "-g", "daemon off;"]

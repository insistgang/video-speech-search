# Docker 部署指南

本指南介绍如何使用 Docker 将视频画面内容检索平台部署到任意环境。

## 环境要求

- Docker Engine 20.10+
- Docker Compose 2.0+
- 4GB+ 可用内存
- 20GB+ 磁盘空间（用于视频和帧存储）

## 快速开始

### 1. 准备环境变量

复制示例文件并配置：

```bash
cp .env.example .env
```

编辑 `.env` 文件，设置必要的环境变量：

```bash
# 必需：Moonshot API Key（如需使用 AI 分析功能）
MOONSHOT_API_KEY=your-api-key-here

# 可选：其他配置
VISION_ANALYZER_MODE=live      # live | mock | kimi_cli
FRAME_INTERVAL=3               # 帧提取间隔（秒）
API_CONCURRENCY=3              # 并发 API 调用数
```

### 2. 启动服务

```bash
docker-compose up -d
```

服务将在后台启动：
- 前端：http://localhost
- 后端 API：http://localhost:8000
- API 文档：http://localhost:8000/docs

### 3. 验证部署

```bash
# 查看服务状态
docker-compose ps

# 查看日志
docker-compose logs -f backend
docker-compose logs -f frontend

# 健康检查
curl http://localhost/api/health
```

## 数据持久化

Docker 部署使用以下卷进行数据持久化：

| 主机路径 | 容器路径 | 用途 |
|---------|---------|------|
| `./data/db` | `/app/data/db` | SQLite 数据库 |
| `./data/frames` | `/app/data/frames` | 提取的帧图片 |
| `${VIDEO_IMPORT_PATH}` | `/app/videos` | 视频导入目录（只读） |

**注意**：删除容器不会丢失数据，数据存储在主机的 `./data` 目录中。

## 常用命令

```bash
# 停止服务
docker-compose down

# 停止并删除数据卷（⚠️ 会删除所有数据）
docker-compose down -v

# 重新构建镜像
docker-compose build --no-cache

# 查看实时日志
docker-compose logs -f

# 进入后端容器执行命令
docker-compose exec backend bash

# 更新到最新代码后重新部署
docker-compose up -d --build
```

## 生产环境部署

### 使用 HTTPS

推荐使用反向代理（如 Nginx、Traefik、Caddy）处理 HTTPS：

```yaml
# docker-compose.prod.yml
version: '3.8'

services:
  backend:
    build:
      context: .
      dockerfile: backend/Dockerfile
    environment:
      - MOONSHOT_API_KEY=${MOONSHOT_API_KEY}
      - VISION_ANALYZER_MODE=live
    volumes:
      - /var/lib/video-search/db:/app/data/db
      - /var/lib/video-search/frames:/app/data/frames
    restart: always

  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    restart: always

  # 使用 Caddy 自动 HTTPS
  caddy:
    image: caddy:2-alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile
      - caddy_data:/data
      - caddy_config:/config
    restart: always

volumes:
  caddy_data:
  caddy_config:
```

Caddyfile 示例：

```
your-domain.com {
    reverse_proxy frontend:80
}

api.your-domain.com {
    reverse_proxy backend:8000
}
```

### 环境变量配置建议

生产环境建议将敏感信息存储在 Docker Secrets 或环境文件中：

```bash
# 创建环境文件
echo "MOONSHOT_API_KEY=sk-xxx" > .env.prod
echo "VISION_ANALYZER_MODE=live" >> .env.prod

# 使用指定环境文件启动
docker-compose --env-file .env.prod -f docker-compose.yml -f docker-compose.prod.yml up -d
```

## 迁移数据

### 从旧环境迁移到新服务器

1. **备份数据**：
```bash
# 在原服务器上
tar czvf video-search-backup.tar.gz data/ .env
```

2. **传输到新服务器**：
```bash
scp video-search-backup.tar.gz user@new-server:/path/
```

3. **在新服务器上恢复**：
```bash
tar xzvf video-search-backup.tar.gz
docker-compose up -d
```

## 故障排查

### 常见问题

1. **后端无法启动**
   ```bash
   # 检查日志
   docker-compose logs backend
   
   # 常见原因：FFmpeg 未安装（已在 Dockerfile 中解决）
   # 检查 FFmpeg 是否可用
   docker-compose exec backend ffmpeg -version
   ```

2. **前端无法连接后端**
   - 检查后端是否正常运行：`curl http://localhost:8000/api/health`
   - 检查 Nginx 配置中的代理地址

3. **数据库权限错误**
   ```bash
   # 修复权限
   sudo chown -R 1000:1000 ./data
   ```

4. **磁盘空间不足**
   ```bash
   # 清理 Docker 缓存
   docker system prune -a
   
   # 检查数据目录大小
   du -sh ./data/frames
   ```

## 更新部署

当代码更新后，重新部署：

```bash
# 拉取最新代码
git pull

# 重新构建并启动
docker-compose down
docker-compose up -d --build

# 如果需要清理旧镜像
docker image prune -f
```

## 资源限制

为容器设置资源限制（防止内存溢出）：

```yaml
services:
  backend:
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 2G
        reservations:
          cpus: '1'
          memory: 512M
```

## 备份策略

建议设置定时备份：

```bash
# 创建备份脚本 backup.sh
#!/bin/bash
BACKUP_DIR="/backup/video-search/$(date +%Y%m%d)"
mkdir -p $BACKUP_DIR

# 备份数据库
cp data/db/search.db $BACKUP_DIR/

# 备份环境变量
cp .env $BACKUP_DIR/

# 压缩并保留最近 7 天
tar czvf $BACKUP_DIR.tar.gz -C /backup/video-search $(date +%Y%m%d)
find /backup/video-search -name "*.tar.gz" -mtime +7 -delete
```

添加到 crontab：
```bash
0 2 * * * /path/to/backup.sh
```

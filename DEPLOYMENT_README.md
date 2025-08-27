# BOCRA Backend Deployment Guide

## Quick Deployment to VPS

### Prerequisites
- SSH access to your VPS server: `ssh root@45.159.230.42 -p 1511`
- SSH key authentication configured
- Server with at least 2GB RAM and 10GB storage

### One-Command Deployment

Run the deployment script from your local machine:

```bash
./deploy.sh
```

This will:
1. ✅ Create a deployment archive with all necessary files
2. ✅ Upload to your VPS server
3. ✅ Install Docker and Docker Compose
4. ✅ Set up PostgreSQL and Redis databases
5. ✅ Build and start the BOCRA API
6. ✅ Configure Nginx reverse proxy
7. ✅ Set up firewall rules
8. ✅ Initialize the database schema

### Manual Deployment Steps

If you prefer manual deployment:

1. **Upload files to server:**
   ```bash
   scp -P 1511 -r backend/ database/ docker-compose.yml Dockerfile nginx.conf .env.example root@45.159.230.42:/opt/bocra/
   ```

2. **SSH into server:**
   ```bash
   ssh root@45.159.230.42 -p 1511
   ```

3. **Install Docker:**
   ```bash
   curl -fsSL https://get.docker.com | sh
   curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-Linux-x86_64" -o /usr/local/bin/docker-compose
   chmod +x /usr/local/bin/docker-compose
   ```

4. **Configure environment:**
   ```bash
   cd /opt/bocra
   cp .env.example .env
   # Edit .env with secure passwords and keys
   ```

5. **Start services:**
   ```bash
   docker-compose up -d
   ```

### After Deployment

- **API Health Check:** http://45.159.230.42:8000/api/health
- **API Documentation:** http://45.159.230.42:8000/api/docs
- **Frontend Update:** Update your Cloudflare Pages frontend to use the new API URL

### Service Management

```bash
# View logs
docker-compose logs -f

# Restart services
docker-compose restart

# Stop services
docker-compose down

# Update deployment
docker-compose pull && docker-compose up -d
```

### Security Notes

- ✅ Firewall configured to allow only necessary ports
- ✅ All passwords auto-generated and secured
- ✅ Services run as non-root users
- ✅ Rate limiting configured in Nginx
- ✅ CORS properly configured for your frontend

### Troubleshooting

1. **Check service status:**
   ```bash
   docker-compose ps
   ```

2. **Check logs:**
   ```bash
   docker-compose logs api
   docker-compose logs postgres
   docker-compose logs redis
   ```

3. **Test database connection:**
   ```bash
   docker-compose exec postgres psql -U bocra -d bocra -c "SELECT version();"
   ```

4. **Test Redis:**
   ```bash
   docker-compose exec redis redis-cli ping
   ```

### File Structure

```
/opt/bocra/
├── backend/              # Python API code
├── database/            # Database schema
├── docker-compose.yml   # Service orchestration
├── Dockerfile          # Container configuration
├── nginx.conf          # Reverse proxy config
├── .env                # Environment variables
└── deploy.sh           # Deployment script
```

### Environment Variables

Key environment variables in `.env`:
- `DATABASE_URL` - PostgreSQL connection string
- `REDIS_URL` - Redis connection string
- `BOCRA_SECRET_KEY` - JWT signing key
- `BOCRA_STORAGE_KEY` - File encryption key
- `FRONTEND_URLS` - Allowed CORS origins

The deployment script generates secure random values for all keys automatically.
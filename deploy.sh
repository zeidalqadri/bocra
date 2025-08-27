#!/bin/bash

# BOCRA Backend Deployment Script
# Deploy to VPS server: ssh root@45.159.230.42 -p 1511

set -e  # Exit on any error

echo "🚀 Starting BOCRA Backend Deployment"
echo "=================================="

# Configuration
SERVER_HOST="45.159.230.42"
SERVER_PORT="1511"
SERVER_USER="root"
DEPLOY_DIR="/opt/bocra"
BACKUP_DIR="/opt/bocra-backup"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if SSH key is available
check_ssh_connection() {
    print_status "Checking SSH connection to server..."
    if ssh -p $SERVER_PORT -o ConnectTimeout=10 -o BatchMode=yes $SERVER_USER@$SERVER_HOST exit 2>/dev/null; then
        print_success "SSH connection successful"
    else
        print_error "SSH connection failed. Please check your SSH key and server access."
        exit 1
    fi
}

# Create deployment archive
create_deployment_archive() {
    # Create temporary directory
    TEMP_DIR=$(mktemp -d)
    ARCHIVE_NAME="bocra-deploy-$(date +%Y%m%d-%H%M%S).tar.gz"
    
    # Copy files to temp directory
    cp -r backend/ $TEMP_DIR/
    cp -r database/ $TEMP_DIR/
    cp docker-compose.yml $TEMP_DIR/
    cp Dockerfile $TEMP_DIR/
    cp nginx.conf $TEMP_DIR/
    cp .env.example $TEMP_DIR/
    cp ocr_fulltext.py $TEMP_DIR/
    
    # Create requirements file in root for Docker
    cp requirements.txt $TEMP_DIR/requirements-main.txt 2>/dev/null || true
    
    # Create archive
    cd $TEMP_DIR
    tar -czf "/tmp/$ARCHIVE_NAME" .
    cd - > /dev/null
    
    # Cleanup
    rm -rf $TEMP_DIR
    
    echo "/tmp/$ARCHIVE_NAME"
}

# Deploy to server
deploy_to_server() {
    local archive_path=$1
    local archive_name=$(basename $archive_path)
    
    print_status "Uploading deployment archive to server..."
    
    # Upload archive
    scp -P $SERVER_PORT $archive_path $SERVER_USER@$SERVER_HOST:/tmp/
    
    # Deploy on server
    ssh -p $SERVER_PORT $SERVER_USER@$SERVER_HOST << EOF
        set -e
        
        echo "📦 Setting up BOCRA on server..."
        
        # Update system
        apt update && apt upgrade -y
        
        # Install Docker if not present
        if ! command -v docker &> /dev/null; then
            echo "🐳 Installing Docker..."
            curl -fsSL https://get.docker.com | sh
            systemctl enable docker
            systemctl start docker
        fi
        
        # Install Docker Compose if not present
        if ! command -v docker-compose &> /dev/null; then
            echo "🐳 Installing Docker Compose..."
            curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-Linux-x86_64" -o /usr/local/bin/docker-compose
            chmod +x /usr/local/bin/docker-compose
        fi
        
        # Install additional system packages
        apt install -y curl wget unzip nginx certbot python3-certbot-nginx ufw
        
        # Create backup if deployment exists
        if [ -d "$DEPLOY_DIR" ]; then
            echo "💾 Creating backup of existing deployment..."
            mkdir -p $BACKUP_DIR
            cp -r $DEPLOY_DIR $BACKUP_DIR/bocra-backup-\$(date +%Y%m%d-%H%M%S)
            
            # Stop existing services
            cd $DEPLOY_DIR
            docker-compose down || true
        fi
        
        # Create deployment directory
        mkdir -p $DEPLOY_DIR
        cd $DEPLOY_DIR
        
        # Extract new deployment
        echo "📂 Extracting deployment files..."
        tar -xzf /tmp/$archive_name
        
        # Setup environment file if it doesn't exist
        if [ ! -f .env ]; then
            echo "⚙️  Creating environment configuration..."
            cp .env.example .env
            
            # Generate secure passwords and keys
            POSTGRES_PW=\$(openssl rand -base64 32 | tr -d "=+/" | cut -c1-25)
            REDIS_PW=\$(openssl rand -base64 32 | tr -d "=+/" | cut -c1-25)
            SECRET_KEY=\$(openssl rand -base64 64 | tr -d "=+/" | cut -c1-50)
            STORAGE_KEY=\$(openssl rand -base64 64 | tr -d "=+/" | cut -c1-50)
            IP_SALT=\$(openssl rand -base64 32 | tr -d "=+/" | cut -c1-25)
            
            # Update .env file
            sed -i "s/your_secure_postgres_password_here/\$POSTGRES_PW/g" .env
            sed -i "s/your_secure_redis_password_here/\$REDIS_PW/g" .env
            sed -i "s/your-very-secure-secret-key-32-characters-min/\$SECRET_KEY/g" .env
            sed -i "s/your-very-secure-storage-encryption-key/\$STORAGE_KEY/g" .env
            sed -i "s/your-secure-ip-hashing-salt/\$IP_SALT/g" .env
            
            echo "🔑 Generated secure passwords and keys"
        fi
        
        # Build and start services
        echo "🏗️  Building and starting BOCRA services..."
        docker-compose build
        docker-compose up -d
        
        # Wait for services to be healthy
        echo "⏳ Waiting for services to start..."
        sleep 30
        
        # Initialize database
        echo "🗄️  Initializing database..."
        docker-compose exec -T postgres psql -U bocra -d bocra -f /docker-entrypoint-initdb.d/schema.sql || echo "Database already initialized"
        
        # Setup firewall
        echo "🔒 Configuring firewall..."
        ufw --force enable
        ufw allow ssh
        ufw allow 80
        ufw allow 443
        ufw allow 8000  # API port
        
        # Cleanup
        rm /tmp/$archive_name
        
        echo "✅ BOCRA deployment completed successfully!"
        echo ""
        echo "🌐 API Health Check: http://$SERVER_HOST:8000/api/health"
        echo "📖 API Documentation: http://$SERVER_HOST:8000/api/docs"
        echo ""
        echo "🔧 To manage the services:"
        echo "   docker-compose logs -f     # View logs"
        echo "   docker-compose restart     # Restart services"
        echo "   docker-compose down        # Stop services"
        echo "   docker-compose up -d       # Start services"
        echo ""
        echo "📁 Deployment location: $DEPLOY_DIR"
EOF
    
    # Cleanup local archive
    rm $archive_path
}

# Test deployment
test_deployment() {
    print_status "Testing deployment..."
    
    # Test health endpoint
    sleep 10
    if curl -f -s "http://$SERVER_HOST:8000/api/health" > /dev/null; then
        print_success "API health check passed"
    else
        print_warning "API health check failed - service might still be starting"
        print_status "You can check the logs with: ssh -p $SERVER_PORT $SERVER_USER@$SERVER_HOST 'cd $DEPLOY_DIR && docker-compose logs -f'"
    fi
}

# Main deployment process
main() {
    print_status "Starting deployment process..."
    
    # Check prerequisites
    if ! command -v ssh &> /dev/null; then
        print_error "SSH client not found. Please install SSH."
        exit 1
    fi
    
    if ! command -v scp &> /dev/null; then
        print_error "SCP not found. Please install SSH/SCP."
        exit 1
    fi
    
    # Check SSH connection
    check_ssh_connection
    
    # Create deployment archive
    print_status "Preparing deployment files..."
    print_status "Creating deployment archive..."
    archive_path=$(create_deployment_archive)
    print_success "Created deployment archive: $archive_path"
    
    # Deploy to server
    deploy_to_server $archive_path
    
    # Test deployment
    test_deployment
    
    print_success "🎉 BOCRA backend deployment completed!"
    print_status "API URL: http://$SERVER_HOST:8000/api"
    print_status "Health Check: http://$SERVER_HOST:8000/api/health"
    print_status "Documentation: http://$SERVER_HOST:8000/api/docs"
    
    echo ""
    print_status "Next steps:"
    echo "1. Update your frontend API URL to: http://$SERVER_HOST:8000/api"
    echo "2. Test the API endpoints"
    echo "3. Configure SSL certificate if needed"
    echo "4. Set up monitoring and backups"
}

# Run main function
main "$@"
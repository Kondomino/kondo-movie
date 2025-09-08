#!/bin/bash

# Script to run local containerized app connected to Render's cloud database
# This allows testing the production database connection locally

set -e  # Exit on any error

echo "🚀 Starting Local App with Render Cloud Database"
echo "=================================================="

# Check if .env.prod exists
if [ ! -f ".env.prod" ]; then
    echo "❌ Error: .env.prod file not found"
    echo "💡 Please create .env.prod with your Render database credentials"
    echo "   Example content:"
    echo "   ENVIRONMENT=prod"
    echo "   RENDER_HOSTNAME=your-db.oregon-postgres.render.com"
    echo "   RENDER_DB_PORT=5432"
    echo "   RENDER_USR=your-username"
    echo "   RENDER_PWD=your-password"
    echo "   RENDER_DB=your-database"
    exit 1
fi

echo "✅ Found .env.prod file"

# Validate database connection first
echo ""
echo "🔍 Validating Render database connection..."
if ! poetry run python scripts/validate_prod_db_connection.py; then
    echo "❌ Database validation failed"
    echo "💡 Please check your .env.prod credentials and ensure Render database is accessible"
    exit 1
fi

echo ""
echo "✅ Database validation successful"

# Stop any existing containers
echo ""
echo "🛑 Stopping existing containers..."
docker-compose -f docker-compose.prod-db.yml down 2>/dev/null || true

# Build the image
echo ""
echo "🏗️  Building Docker image..."
docker-compose -f docker-compose.prod-db.yml build

# Start the application
echo ""
echo "🚀 Starting application with cloud database..."
echo "📊 Environment: PRODUCTION"
echo "🗄️  Database: Render PostgreSQL (Cloud)"
echo "🌐 App will be available at: http://localhost:8080"
echo ""
echo "⚠️  WARNING: You are connecting to the PRODUCTION database!"
echo "   - Be careful with data modifications"
echo "   - Consider using read-only operations for testing"
echo ""

# Ask for confirmation
read -p "Do you want to continue? (y/N): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "❌ Aborted by user"
    exit 1
fi

echo "🚀 Starting containers..."
docker-compose -f docker-compose.prod-db.yml up

echo ""
echo "🏁 Application stopped"

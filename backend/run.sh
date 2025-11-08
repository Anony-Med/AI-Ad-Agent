#!/bin/bash

# AI Ad Agent - Development Runner Script

set -e

echo "🚀 Starting AI Ad Agent..."

# Check if .env exists
if [ ! -f .env ]; then
    echo "⚠️  .env file not found. Copying from .env.example..."
    cp .env.example .env
    echo "⚠️  Please update .env with your configuration before running again."
    exit 1
fi

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "🔧 Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo "📥 Installing dependencies..."
pip install -q --upgrade pip
pip install -q -e .

# Run the application
echo "✅ Starting FastAPI server..."
echo "📖 API Documentation: http://localhost:8000/docs"
echo "📚 ReDoc: http://localhost:8000/redoc"
echo ""

uvicorn main:app --reload --host 0.0.0.0 --port 8000

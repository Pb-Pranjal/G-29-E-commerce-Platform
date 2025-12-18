#!/usr/bin/env bash
set -e

# Build script for Render / deployment
# Usage:
#   chmod +x build.sh
#   ./build.sh

echo "Installing Python dependencies..."
pip install -r requirements.txt

echo "Collecting static files..."
python manage.py collectstatic --noinput

echo "Applying database migrations..."
python manage.py migrate

echo "Build script finished successfully." 

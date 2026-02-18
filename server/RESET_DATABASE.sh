#!/bin/bash
# Script to reset the database by dropping all tables
# This is useful when you've made schema changes and need a fresh start

echo "⚠️  WARNING: This will DELETE ALL DATA in the database!"
echo "Press Ctrl+C within 3 seconds to cancel..."
sleep 3

echo ""
echo "Starting server with DROP_TABLES_ON_STARTUP=True..."
export DROP_TABLES_ON_STARTUP=True
python3 server.py

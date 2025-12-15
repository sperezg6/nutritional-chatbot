#!/bin/bash
# Startup script for FastAPI streaming application with uvicorn
exec uvicorn streaming_handler:app --host 0.0.0.0 --port 8080

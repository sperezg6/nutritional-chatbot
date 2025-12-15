#!/bin/bash
# Startup script for FastAPI streaming application with uvicorn
export PYTHONPATH=/var/task:/opt/python:$PYTHONPATH
exec /var/lang/bin/python3.11 -m uvicorn streaming_handler:app --host 0.0.0.0 --port 8080

# ==========================================
# Stage 1: Build the Frontend (React + Vite)
# ==========================================
FROM node:20-alpine AS frontend-builder
WORKDIR /build/frontend

# Copy package files first to leverage Docker layer caching
COPY frontend/package*.json ./
RUN npm install

# Copy the rest of the frontend source and build
COPY frontend/ ./
RUN npm run build

# ==========================================
# Stage 2: Build the Backend and Serve
# ==========================================
FROM python:3.11-slim

# Prevent Python from writing pyc files and keep stdout unbuffered
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Set work directory to /app
WORKDIR /app

# Install system dependencies required for some Python packages (e.g., ChromaDB, PyMySQL)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy only the requirements file first to leverage Docker layer caching
COPY backend/requirements.txt /app/backend/

WORKDIR /app/backend

# IMPORTANT: Install PyTorch CPU version first to prevent downloading the 2.5GB CUDA version
RUN pip install --no-cache-dir torch==2.14.0 torchvision==0.29.0 --index-url https://download.pytorch.org/whl/cpu

# Install the rest of the backend requirements
RUN pip install --no-cache-dir -r requirements.txt

# Copy the backend code
COPY backend/ /app/backend/

# Copy the built frontend assets from Stage 1
# The backend config resolves FRONTEND_DIST to BASE_DIR.parent / "frontend" / "dist"
# which translates to /app/frontend/dist
COPY --from=frontend-builder /build/frontend/dist /app/frontend/dist

# Expose the FastAPI port
EXPOSE 8000

# Run the FastAPI application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

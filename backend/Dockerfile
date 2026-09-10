FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/

# Install PyTorch CPU version first to prevent downloading the 2.5GB CUDA version
RUN pip install --no-cache-dir torch==2.14.0 torchvision==0.29.0 --index-url https://download.pytorch.org/whl/cpu

# Install the rest of the backend requirements
RUN pip install --no-cache-dir -r requirements.txt

# Copy the backend code
COPY . /app/

# We're deploying the frontend separately as a static site, so we don't need to serve it here.
# Expose the FastAPI port
EXPOSE 8000

# Run the FastAPI application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

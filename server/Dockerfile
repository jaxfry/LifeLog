# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set the working directory in the container
WORKDIR /app

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# --- Install third-party dependencies ---
# Copy only the requirements file first to leverage Docker cache
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# --- Pre-download embedding model ---
# Download the sentence-transformers model at build time to avoid runtime failures
# This ensures the model is available even without internet access at runtime
RUN python3 -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')"

# --- Install our local application code ---
# Copy the pyproject.toml and the src directory
COPY pyproject.toml .
COPY ./src /app/src

# Install our application in editable mode inside the container
RUN pip install -e .

# The command to run the application will be provided by docker-compose
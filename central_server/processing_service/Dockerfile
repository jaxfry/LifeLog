# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file into the container at /app/central_server/processing_service
COPY central_server/processing_service/requirements.txt ./central_server/processing_service/

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r ./central_server/processing_service/requirements.txt

# Copy the entire central_server directory into the container at /app/central_server
COPY central_server ./central_server

# Set the working directory to the processing_service directory
WORKDIR /app/central_server/processing_service

# Command to run the worker script
CMD ["python", "worker.py"]
# Use Python base image
FROM python:3.12-slim

# Install system dependencies
RUN apt-get update && apt-get install -y 
    curl 
    && rm -rf /var/lib/apt/lists/*

# Install Ollama
RUN curl -fsSL https://ollama.com/install.sh | sh

# Set working directory
WORKDIR /app

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the code
COPY . .

# Expose ports for Ollama and any other services
EXPOSE 11434 8080

# Script to start Ollama and the Bot
RUN echo '#!/bin/bash

ollama serve &

sleep 5

ollama pull llama3.2:3b

python slack_bot.py' > /app/start.sh
RUN chmod +x /app/start.sh

CMD ["/app/start.sh"]

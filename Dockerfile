# Use official Python base image
FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the bot code
COPY bot.py .
COPY .env .

# Run the bot
CMD ["python", "bot.py"]

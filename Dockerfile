FROM python:3.11-slim

# Install CA certificates
RUN apt-get update && apt-get install -y ca-certificates

# Set working directory
WORKDIR /app

# Copy your app files
COPY . /app

# Install dependencies
RUN pip install --upgrade pip && pip install -r requirements.txt

# Expose port
EXPOSE 10000

# Run the app
CMD ["gunicorn", "-b", "0.0.0.0:10000", "app:app"]

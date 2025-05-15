FROM python:3.11-slim

# Install CA certificates
RUN apt-get update && apt-get install -y ca-certificates

# Set working directory to root (where your code is)
WORKDIR /app

# Copy everything to container
COPY . .

# Install Python dependencies
RUN pip install --upgrade pip && pip install -r requirements.txt

# Expose the port your app runs on
EXPOSE 10000

# Start the app
CMD ["gunicorn", "-b", "0.0.0.0:10000", "app:app"]

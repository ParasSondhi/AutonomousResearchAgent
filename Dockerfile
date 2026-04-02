# Use a lightweight Python Linux image
FROM python:3.11-slim

# Install the system-level wkhtmltopdf package
RUN apt-get update && apt-get install -y wkhtmltopdf && rm -rf /var/lib/apt/lists/*

# Set the working directory inside the container
WORKDIR /app

# Copy your requirements file and install Python packages
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all your project files into the container
COPY . .

# Tell Docker which port the app runs on
EXPOSE 8000

# The command to start your FastAPI server
CMD ["uvicorn", "main:api", "--host", "0.0.0.0", "--port", "8000"]
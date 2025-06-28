FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    libldap2-dev \
    libsasl2-dev \
    python3-dev \
    default-libmysqlclient-dev \
    default-mysql-client \
    pkg-config \
    dos2unix \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create the application directory
WORKDIR /code

# Copy dependency files
COPY app/requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the code
COPY app ./app

# Create the directory for certificates
RUN mkdir -p /code/app/certs

# Compile translation files
RUN if [ -d "app/translations" ]; then \
    pybabel compile -d app/translations; \
fi

# Copy and configure the startup script
COPY app/start.sh /start.sh
RUN chmod +x /start.sh && dos2unix /start.sh

# Expose the port
EXPOSE 5000

# Startup script
CMD ["/start.sh"]
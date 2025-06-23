#!/bin/sh

# Load environment variables from the .env file
if [ -f "/app/.env" ]; then
    echo "Loading environment variables from .env..."
    # Use set -a to automatically export all variables
    set -a
    . /app/.env
    set +a
    echo "Environment variables loaded successfully."
else
    echo ".env file not found, using default values."
    # Define default values if the .env file does not exist
    export DB_HOST=db
    export DB_USER=listing_user
    export DB_PASSWORD=listing_password
    export DB_NAME=listing_db
    export DB_PORT=3306
    export FLASK_ENV=development
    export FLASK_APP=app.py
fi

# Function to generate self-signed SSL certificates
generate_ssl_certificates() {
    echo "Checking SSL certificates..."
    SSL_DIR="/app/ssl"
    
    # Create the SSL directory if it doesn't exist
    if [ ! -d "$SSL_DIR" ]; then
        echo "Creating SSL directory..."
        mkdir -p "$SSL_DIR"
    fi
    
    # Check if cert.crt or cert.key are directories and delete them if so
    for cert_file in "cert.crt" "cert.key" "CA.crt"; do
        if [ -d "$SSL_DIR/$cert_file" ]; then
            echo "Warning: $cert_file is a directory. Deleting..."
            rm -rf "$SSL_DIR/$cert_file"
        fi
    done
    
    # Check if the certificates already exist as files
    if [ ! -f "$SSL_DIR/cert.crt" ] || [ ! -f "$SSL_DIR/cert.key" ]; then
        echo "SSL certificates not found or invalid. Generating self-signed certificates..."
        
        # Generate a self-signed certificate valid for localhost and the domain name
        if [ ! -z "$SERVER_NAME" ]; then
            DOMAIN="$SERVER_NAME"
        else
            DOMAIN=${DOMAIN_NAME:-"localhost"}
        fi
        
        echo "Generating certificate for domain: $DOMAIN"
        
        # Create the OpenSSL configuration
        cat > "$SSL_DIR/openssl.cnf" << EOF
[req]
default_bits = 2048
prompt = no
default_md = sha256
distinguished_name = dn
x509_extensions = v3_req

[dn]
C = FR
ST = France
L = Paris
O = List-IQ
OU = Development
CN = $DOMAIN

[v3_req]
subjectAltName = @alt_names
keyUsage = digitalSignature, keyEncipherment
extendedKeyUsage = serverAuth

[alt_names]
DNS.1 = $DOMAIN
DNS.2 = localhost
IP.1 = 127.0.0.1
EOF
        
        # Generate the private key and certificate
        echo "Executing OpenSSL command to generate certificates..."
        openssl req -x509 -nodes -days 3650 -newkey rsa:2048 \
            -keyout "$SSL_DIR/cert.key" -out "$SSL_DIR/cert.crt" \
            -config "$SSL_DIR/openssl.cnf"
            
        # Check if generation was successful
        if [ $? -eq 0 ]; then
            echo "SSL certificates generated successfully."
            # Also create a CA.crt file (copy of cert.crt for compatibility)
            cp "$SSL_DIR/cert.crt" "$SSL_DIR/CA.crt"
            # Set appropriate permissions
            chmod 644 "$SSL_DIR/cert.crt" "$SSL_DIR/CA.crt"
            chmod 600 "$SSL_DIR/cert.key"
            
            # Check that the files are valid PEM certificates
            if openssl x509 -in "$SSL_DIR/cert.crt" -noout -text > /dev/null 2>&1; then
                echo "cert.crt certificate validated successfully."
            else
                echo "ERROR: The cert.crt file does not appear to be a valid PEM certificate."
            fi
        else
            echo "Error generating SSL certificates."
        fi
    else
        echo "Existing SSL certificates found."
        
        # Check that the existing certificates are valid
        if ! openssl x509 -in "$SSL_DIR/cert.crt" -noout -text > /dev/null 2>&1; then
            echo "WARNING: The existing certificate does not seem valid. Deleting and regenerating..."
            rm -f "$SSL_DIR/cert.crt" "$SSL_DIR/cert.key" "$SSL_DIR/CA.crt"
            # Call the function again to regenerate certificates
            generate_ssl_certificates
            return
        fi
    fi
}

# Call the function to generate SSL certificates
generate_ssl_certificates

# Display environment variables for debugging
echo "Database configuration:"
echo "DB_HOST=$DB_HOST"
echo "DB_USER=$DB_USER"
echo "DB_NAME=$DB_NAME"
echo "DB_PORT=$DB_PORT"

# Wait for the database to be ready
echo "Waiting for database..."

# Check if the mysql-client package is installed
# if ! command -v mysqladmin &> /dev/null; then
#     echo "mysql-client is not installed. Installing..."
#     apt-get update && apt-get install -y default-mysql-client
# fi

# Install mysql-connector-python if not already installed
#if ! python -c "import mysql.connector" &> /dev/null; then
#    echo "mysql-connector-python is not installed. Installing..."
#    pip install mysql-connector-python
#fi

# Wait for the database to be accessible
max_retries=60
counter=0
while [ $counter -lt $max_retries ]; do
    # First, try with the normal user
    if mysqladmin ping -h "$DB_HOST" -u "$DB_USER" -p"$DB_PASSWORD" --silent; then
        echo "Database ready with $DB_USER!"
        break
    fi
    
    # If that doesn't work, try with root
    if mysqladmin ping -h "$DB_HOST" -u root -proot --silent; then
        echo "Database ready with root!"
        break
    fi
    
    counter=$((counter + 1))
    echo "Waiting for database... ($counter/$max_retries)"
    sleep 2
    
    # If we reach half the attempts, display diagnostic information
    if [ $counter -eq 30 ]; then
        echo "Network diagnostics:"
        ping -c 1 db || echo "Cannot ping the db server"
        netstat -tulpn || echo "netstat not available"
        
        # Check if MySQL is running
        echo "Checking MySQL status:"
        telnet "$DB_HOST" "$DB_PORT" || echo "Cannot connect to the MySQL port"
    fi
done

if [ $counter -ge $max_retries ]; then
    echo "Error: Could not connect to the database after $max_retries attempts."
    echo "Check that the database container is running and accessible."
    echo "Attempting to start the application despite the error..."
fi

# Run migration scripts only if NEW_INSTALL=true or UPDATE=true
if [ "$NEW_INSTALL" = "true" ] || [ "$UPDATE" = "true" ]; then
    # Environment variables for migration scripts are already defined in the .env file
    # But we export them anyway to ensure compatibility with existing scripts
    export MYSQL_HOST="$DB_HOST"
    export MYSQL_USER="$DB_USER"
    export MYSQL_PASSWORD="$DB_PASSWORD"
    export MYSQL_DATABASE="$DB_NAME"
    export MYSQL_PORT="$DB_PORT"

fi

# Create the database structure from the SQL file only if NEW_INSTALL=true
if [ "$UPDATE" = "true" ]; then
    echo "MIGRATING..."
   python migrations/upgrade.py || echo "Error during migration"
else
    echo "Skipping migration (set UPDATE=true to force)"
fi

# The database structure is now managed by init.sql on MySQL container startup
# We no longer need to import db_structure.sql here
if [ "$NEW_INSTALL" = "true" ]; then
    echo "The database structure is now initialized via init.sql on MySQL container startup."
fi

# The following section for checking and creating tables is commented out as it's handled by init.sql
# ...

# Run the admin user creation script only if NEW_INSTALL=true or RESET_ADMIN=true
if [ "$NEW_INSTALL" = "true" ] || [ "$RESET_ADMIN" = "true" ]; then
    echo "Creating/Resetting admin user..."
    python create_admin.py || echo "Error creating admin user"
else
    echo "Skipping admin user creation/reset (set NEW_INSTALL=true or RESET_ADMIN=true to force)"
fi

# Create the directory for public files if it doesn't exist
if [ "$NEW_INSTALL" = "true" ]; then
    echo "Creating public files directory..."
    mkdir -p /app/public
    chmod 777 /app/public
fi

# Get the SSL certificate if necessary
echo "Checking SSL certificate..."
SSL_CERT_PATH="/app/certs/custom_ca.pem"
SSL_CERT_URL=${SSL_CERT_URL:-""}

if [ ! -f "$SSL_CERT_PATH" ] && [ ! -z "$SSL_CERT_URL" ]; then
    echo "Downloading SSL certificate from $SSL_CERT_URL..."
    python /app/scripts/install_certificate.py --url "$SSL_CERT_URL" --output "$SSL_CERT_PATH"
    if [ $? -eq 0 ]; then
        echo "SSL certificate installed successfully."
        # Enable SSL verification in the application
        export VERIFY_SSL_CERTIFICATES=true
    else
        echo "Failed to install SSL certificate. SSL verification will be disabled."
        export VERIFY_SSL_CERTIFICATES=false
    fi
else
    if [ -f "$SSL_CERT_PATH" ]; then
        echo "SSL certificate already present. SSL verification will be enabled."
        export VERIFY_SSL_CERTIFICATES=true
    else
        echo "No SSL certificate found and no URL provided. SSL verification will be disabled."
        export VERIFY_SSL_CERTIFICATES=false
    fi
fi

# Start the Flask application
echo "Starting Flask application..."

# Force development mode to enable auto-reloading
export FLASK_ENV=development
echo "FLASK_ENV=$FLASK_ENV"

# Add the --reload option in development mode to automatically reload templates
if [ "$FLASK_ENV" = "development" ]; then
    echo "Development mode detected, enabling auto-reload..."
    gunicorn --bind 0.0.0.0:5000 --reload wsgi:app
else
    echo "Production mode, no auto-reload."
    gunicorn --bind 0.0.0.0:5000 wsgi:app
fi
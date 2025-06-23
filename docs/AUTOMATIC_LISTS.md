# List-IQ Automatic Lists Guide

## Introduction

Automatic lists are a powerful feature of List-IQ that allow for the automatic updating of a list's content from external sources. This guide explains how to configure and use this feature.

## Types of Automatic Lists

List-IQ supports several types of sources for automatic lists:

1.  **URL** - Data retrieval from a remote URL
2.  **API** - Connection to an external API
3.  **File** - Monitoring of a local file
4.  **Database** - Querying a database

## Configuring an Automatic List

### Step 1: Create a New List

Start by creating a new list via the List-IQ web interface:

1.  Log in to the administration interface
2.  Click "Lists" in the main menu
3.  Click "New List"
4.  Fill in the basic information (name, description)
5.  Check the "Automatic List" option
6.  Select the source type

### Step 2: Configure the Source

Depending on the selected source type, you will need to provide specific information:

#### URL Source

```json
{
  "url": "https://example.com/data.json",
  "method": "GET",
  "headers": {
    "Authorization": "Bearer your_token"
  },
  "data_path": "results.items",
  "refresh_interval": 3600
}


url: The URL of the data source

method: HTTP method (GET, POST, etc.)

headers: HTTP headers to include

data_path: JSON path to extract the data

refresh_interval: Refresh interval in seconds

API Source
Generated json
{
  "api_url": "https://api.example.com/v1/products",
  "api_key": "your_api_key",
  "api_secret": "your_api_secret",
  "parameters": {
    "limit": 100,
    "category": "electronics"
  },
  "data_path": "data",
  "refresh_interval": 3600
}
IGNORE_WHEN_COPYING_START
content_copy
download
Use code with caution.
Json
IGNORE_WHEN_COPYING_END

api_url: API URL

api_key: API key (if necessary)

api_secret: API secret (if necessary)

parameters: Parameters to send to the API

data_path: JSON path to extract the data

refresh_interval: Refresh interval in seconds

File Source
Generated json
{
  "file_path": "/data/products.csv",
  "file_format": "csv",
  "delimiter": ",",
  "has_header": true,
  "encoding": "utf-8",
  "watch_for_changes": true
}
IGNORE_WHEN_COPYING_START
content_copy
download
Use code with caution.
Json
IGNORE_WHEN_COPYING_END

file_path: Path to the file

file_format: File format (csv, json, xml)

delimiter: Delimiter for CSV files

has_header: Indicates if the CSV file has a header row

encoding: File encoding

watch_for_changes: Watch for file changes

Database Source
Generated json
{
  "db_type": "mysql",
  "host": "db.example.com",
  "port": 3306,
  "database": "products_db",
  "username": "user",
  "password": "password",
  "query": "SELECT id, name, price, category FROM products WHERE active = 1",
  "refresh_interval": 3600
}
IGNORE_WHEN_COPYING_START
content_copy
download
Use code with caution.
Json
IGNORE_WHEN_COPYING_END

db_type: Database type (mysql, postgresql, sqlite)

host: Database host

port: Database port

database: Database name

username: Username

password: Password

query: SQL query

refresh_interval: Refresh interval in seconds

Step 3: Configure Field Mapping

Once the source is configured, you must define how the source data is mapped to the fields of your list:

Generated json
{
  "mappings": {
    "id": "product_id",
    "name": "product_name",
    "description": "product_description",
    "price": "price_usd",
    "category": "category_name"
  },
  "transformations": {
    "price": "value * 0.85",
    "category": "value.toUpperCase()"
  }
}
IGNORE_WHEN_COPYING_START
content_copy
download
Use code with caution.
Json
IGNORE_WHEN_COPYING_END

mappings: Correspondence between list fields and source fields

transformations: Transformations to apply to values (JavaScript expressions)

Step 4: Configure Update Options

Finally, configure how updates should be handled:

Generated json
{
  "update_strategy": "merge",
  "key_field": "id",
  "delete_missing": false,
  "max_items": 1000,
  "notify_on_update": true,
  "error_handling": "log"
}
IGNORE_WHEN_COPYING_START
content_copy
download
Use code with caution.
Json
IGNORE_WHEN_COPYING_END

update_strategy: Update strategy (replace, merge, append)

key_field: Field used as a key for merging

delete_missing: Delete items that are no longer in the source

max_items: Maximum number of items to keep

notify_on_update: Send a notification upon updates

error_handling: Error handling (log, fail, ignore)

Complete Examples
Product List from an API
Generated json
{
  "source": {
    "type": "api",
    "api_url": "https://api.example.com/v1/products",
    "api_key": "your_api_key",
    "parameters": {
      "limit": 100
    },
    "data_path": "data",
    "refresh_interval": 3600
  },
  "mappings": {
    "id": "id",
    "name": "title",
    "description": "description",
    "price": "price",
    "image": "image_url",
    "category": "category"
  },
  "update_strategy": "merge",
  "key_field": "id",
  "delete_missing": true
}
IGNORE_WHEN_COPYING_START
content_copy
download
Use code with caution.
Json
IGNORE_WHEN_COPYING_END
Contact List from a CSV File
Generated json
{
  "source": {
    "type": "file",
    "file_path": "/data/contacts.csv",
    "file_format": "csv",
    "delimiter": ",",
    "has_header": true,
    "encoding": "utf-8",
    "watch_for_changes": true
  },
  "mappings": {
    "id": "contact_id",
    "name": "full_name",
    "email": "email_address",
    "phone": "phone_number",
    "company": "organization"
  },
  "transformations": {
    "name": "value.toUpperCase()",
    "email": "value.toLowerCase()"
  },
  "update_strategy": "replace"
}
IGNORE_WHEN_COPYING_START
content_copy
download
Use code with caution.
Json
IGNORE_WHEN_COPYING_END
Troubleshooting
Common Issues

The list does not update

Check the refresh interval

Check the logs for errors

Ensure the source is accessible

Missing Data

Check the field mapping

Check the data path (data_path)

Ensure the source contains the expected data

Authentication Errors

Check the API keys and secrets

Check the authentication headers

Slow Performance

Reduce the refresh frequency

Limit the number of items

Optimize database queries

Best Practices

Use reasonable refresh intervals to avoid overloading the sources

Secure credentials (API keys, passwords)

Use transformations to normalize data

Test the configuration with a small dataset before using it in production

Generated code
IGNORE_WHEN_COPYING_START
content_copy
download
Use code with caution.
IGNORE_WHEN_COPYING_END
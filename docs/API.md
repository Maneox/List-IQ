# List-IQ API Documentation

## Introduction

The List-IQ API allows for programmatic interaction with data lists. It provides features to read, add, modify, and delete data in published lists.

## Authentication

The API uses token-based authentication. To get a token, you need to log into the web interface and generate an API token in your user profile.

## Endpoints

### Get All Lists


GET /api/lists

Generated code
**Parameters**
- `token` (required): Your authentication token
- `format` (optional): Output format (json, xml, csv). Default: json

**Example Response**
```json
{
  "status": "success",
  "data": [
    {
      "id": 1,
      "name": "Product List",
      "description": "Product Catalog",
      "items_count": 42,
      "last_updated": "2025-06-15T14:30:00Z"
    },
    {
      "id": 2,
      "name": "Contact List",
      "description": "Professional Contacts",
      "items_count": 18,
      "last_updated": "2025-06-16T09:15:00Z"
    }
  ]
}
IGNORE_WHEN_COPYING_START
content_copy
download
Use code with caution.
IGNORE_WHEN_COPYING_END
Get a Specific List
Generated code
GET /api/lists/{id}
IGNORE_WHEN_COPYING_START
content_copy
download
Use code with caution.
IGNORE_WHEN_COPYING_END

Parameters

token (required): Your authentication token

format (optional): Output format (json, xml, csv). Default: json

Example Response

Generated json
{
  "status": "success",
  "data": {
    "id": 1,
    "name": "Product List",
    "description": "Product Catalog",
    "items": [
      {
        "id": 101,
        "name": "Product A",
        "price": 19.99,
        "category": "Electronics"
      },
      {
        "id": 102,
        "name": "Product B",
        "price": 29.99,
        "category": "IT"
      }
    ],
    "last_updated": "2025-06-15T14:30:00Z"
  }
}
IGNORE_WHEN_COPYING_START
content_copy
download
Use code with caution.
Json
IGNORE_WHEN_COPYING_END
Add an Item to a List
Generated code
POST /api/lists/{id}/items
IGNORE_WHEN_COPYING_START
content_copy
download
Use code with caution.
IGNORE_WHEN_COPYING_END

Headers

Content-Type: application/json

Authorization: Bearer {token}

Request Body

Generated json
{
  "name": "New Product",
  "price": 39.99,
  "category": "Accessories"
}
IGNORE_WHEN_COPYING_START
content_copy
download
Use code with caution.
Json
IGNORE_WHEN_COPYING_END

Example Response

Generated json
{
  "status": "success",
  "message": "Item added successfully",
  "data": {
    "id": 103,
    "name": "New Product",
    "price": 39.99,
    "category": "Accessories"
  }
}
IGNORE_WHEN_COPYING_START
content_copy
download
Use code with caution.
Json
IGNORE_WHEN_COPYING_END
Modify an Item in a List
Generated code
PUT /api/lists/{list_id}/items/{item_id}
IGNORE_WHEN_COPYING_START
content_copy
download
Use code with caution.
IGNORE_WHEN_COPYING_END

Headers

Content-Type: application/json

Authorization: Bearer {token}

Request Body

Generated json
{
  "name": "Modified Product",
  "price": 49.99,
  "category": "Premium Accessories"
}
IGNORE_WHEN_COPYING_START
content_copy
download
Use code with caution.
Json
IGNORE_WHEN_COPYING_END

Example Response

Generated json
{
  "status": "success",
  "message": "Item modified successfully",
  "data": {
    "id": 103,
    "name": "Modified Product",
    "price": 49.99,
    "category": "Premium Accessories"
  }
}
IGNORE_WHEN_COPYING_START
content_copy
download
Use code with caution.
Json
IGNORE_WHEN_COPYING_END
Delete an Item from a List
Generated code
DELETE /api/lists/{list_id}/items/{item_id}
IGNORE_WHEN_COPYING_START
content_copy
download
Use code with caution.
IGNORE_WHEN_COPYING_END

Headers

Authorization: Bearer {token}

Example Response

Generated json
{
  "status": "success",
  "message": "Item deleted successfully"
}
IGNORE_WHEN_COPYING_START
content_copy
download
Use code with caution.
Json
IGNORE_WHEN_COPYING_END
Error Codes

400: Bad Request

401: Unauthorized

403: Forbidden

404: Not Found

500: Server Error

Usage Examples
Python
Generated python
import requests

API_URL = "http://your-server.com/api"
TOKEN = "your_api_token"

# Get all lists
response = requests.get(
    f"{API_URL}/lists",
    params={"token": TOKEN}
)
lists = response.json()["data"]
print(f"Number of lists: {len(lists)}")

# Add an item to a list
new_item = {
    "name": "New Product",
    "price": 39.99,
    "category": "Accessories"
}
response = requests.post(
    f"{API_URL}/lists/1/items",
    headers={"Authorization": f"Bearer {TOKEN}"},
    json=new_item
)
print(f"Status: {response.json()['status']}")
IGNORE_WHEN_COPYING_START
content_copy
download
Use code with caution.
Python
IGNORE_WHEN_COPYING_END
cURL
Generated bash
# Get all lists
curl -X GET "http://your-server.com/api/lists?token=your_api_token"

# Add an item to a list
curl -X POST "http://your-server.com/api/lists/1/items" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your_api_token" \
  -d '{"name":"New Product","price":39.99,"category":"Accessories"}'
IGNORE_WHEN_COPYING_START
content_copy
download
Use code with caution.
Bash
IGNORE_WHEN_COPYING_END
Generated code
--- END OF FILE API.md ---
IGNORE_WHEN_COPYING_START
content_copy
download
Use code with caution.
IGNORE_WHEN_COPYING_END
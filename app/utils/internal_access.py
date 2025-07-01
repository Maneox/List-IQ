import os
from ..models.list import List
from flask import current_app
import json


def get_internal_list_data_from_public_json_url(url):
    """
    If the URL targets a local public JSON endpoint (/public/json/<token>),
    returns the list data directly via ORM (no HTTP call).
    Otherwise returns None.
    """
    # Detect internal domains (adapt if needed)
    from urllib.parse import urlparse
    app_domain = os.environ.get('SERVER_NAME') or current_app.config.get('SERVER_NAME', 'localhost')
    # Extract the target domain/port
    parsed_url = urlparse(url)
    url_netloc = parsed_url.netloc.lower()
    app_domain_clean = app_domain.lower() if app_domain else ''

    # Consider internal if URL's netloc == SERVER_NAME (or local variants)
    is_internal_url = (
        url_netloc == app_domain_clean or
        url_netloc in ["localhost:5000", "web:5000", "nginx"]
    )
    if is_internal_url and "/public/json/" in url:
        # Extract the token
        parts = url.split("/public/json/")
        if len(parts) == 2:
            public_id = parts[1].split("?")[0].strip()
            source_list = List.query.filter_by(public_access_token=public_id).first()
            if source_list:
                # Generate public JSON (keep 'id' if it's a business column)
                data = source_list.get_data()
                business_columns = {col.name for col in source_list.columns}  # Get business columns
                filtered_data = []
                for row in data:
                    # Don't remove 'id' if it's a business column
                    filtered_row = {k: v for k, v in row.items() if k != 'id' or k in business_columns}
                    filtered_data.append(filtered_row)
                current_app.logger.info(f"Internal data retrieved for list {source_list.id} with {len(filtered_data)} rows")
                if filtered_data and len(filtered_data) > 0:
                    current_app.logger.info(f"First row (columns): {list(filtered_data[0].keys())}")
                return filtered_data
            else:
                current_app.logger.error(f"No list found with public token {public_id}")
                return None
        else:
            current_app.logger.error(f"Invalid internal URL format: {url}")
            return None
    return None
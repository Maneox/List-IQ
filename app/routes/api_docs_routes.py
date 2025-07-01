from flask import Blueprint, render_template, send_file, current_app, jsonify
import os
from flask_login import login_required
from .decorators import admin_required
from .public_routes import public_route
import json

api_docs_bp = Blueprint('api_docs', __name__)

@api_docs_bp.route('/api/docs/openapi.yaml')
@public_route
def serve_openapi_spec():
    """Serves the OpenAPI specification file without authentication"""
    # This route is explicitly exempt from authentication
    openapi_path = os.path.join(current_app.root_path, 'docs/openapi.yaml')
    response = send_file(openapi_path, mimetype='text/yaml')
    # Add CORS headers to allow access from any origin
    response.headers['Access-Control-Allow-Origin'] = '*'
    return response

@api_docs_bp.route('/api/docs/postman_collection.json')
@public_route
def serve_postman_collection():
    """Serves the Postman collection file without authentication"""
    # This route is explicitly exempt from authentication
    collection_path = os.path.join(current_app.root_path, 'docs/postman_collection.json')
    response = send_file(collection_path, mimetype='application/json')
    # Add CORS headers to allow access from any origin
    response.headers['Access-Control-Allow-Origin'] = '*'
    return response

@api_docs_bp.route('/api/docs')
@login_required
def api_docs():
    """API documentation page with Swagger UI"""
    return render_template('api_docs.html')

@api_docs_bp.route('/api/docs/postman')
@login_required
def api_docs_postman():
    """Instructions page for Postman integration"""
    return render_template('api_docs_postman.html')
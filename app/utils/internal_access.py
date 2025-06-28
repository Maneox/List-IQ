import os
from ..models.list import List
from flask import current_app
import json


def get_internal_list_data_from_public_json_url(url):
    """
    Si l'URL cible un endpoint public JSON local (/public/json/<token>),
    retourne directement les données de la liste via ORM (pas d'appel HTTP).
    Sinon retourne None.
    """
    # Détection des domaines internes (adapter si besoin)
    from urllib.parse import urlparse
    app_domain = os.environ.get('SERVER_NAME') or current_app.config.get('SERVER_NAME', 'localhost')
    # On extrait le domaine/port de l'URL cible
    parsed_url = urlparse(url)
    url_netloc = parsed_url.netloc.lower()
    app_domain_clean = app_domain.lower() if app_domain else ''

    # On considère interne si le netloc de l'URL == SERVER_NAME (ou variantes locales)
    is_internal_url = (
        url_netloc == app_domain_clean or
        url_netloc in ["localhost:5000", "web:5000", "nginx"]
    )
    if is_internal_url and "/public/json/" in url:
        # Extraction du token
        parts = url.split("/public/json/")
        if len(parts) == 2:
            public_id = parts[1].split("?")[0].strip()
            source_list = List.query.filter_by(public_access_token=public_id).first()
            if source_list:
                # Génération du JSON public (filtrage champ id)
                data = source_list.get_data()
                filtered_data = []
                for row in data:
                    filtered_row = {k: v for k, v in row.items() if k != 'id'}
                    filtered_data.append(filtered_row)
                return filtered_data
            else:
                current_app.logger.error(f"Aucune liste trouvée avec le token public {public_id}")
                return None
        else:
            current_app.logger.error(f"Format d'URL interne invalide : {url}")
            return None
    return None

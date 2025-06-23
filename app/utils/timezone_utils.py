"""
Utilitaires pour la gestion des fuseaux horaires dans l'application.
"""
import pytz
from datetime import datetime, timezone

# Définir le fuseau horaire par défaut pour l'application
PARIS_TIMEZONE = pytz.timezone('Europe/Paris')

def get_paris_now():
    """Retourne la date et l'heure actuelles dans le fuseau horaire de Paris"""
    return datetime.now(PARIS_TIMEZONE)

def utc_to_paris(utc_dt):
    """Convertit une date UTC en date Paris"""
    if not utc_dt:
        return None
    if utc_dt.tzinfo is None:
        utc_dt = utc_dt.replace(tzinfo=timezone.utc)
    return utc_dt.astimezone(PARIS_TIMEZONE)

def format_datetime(dt, format_str='%Y-%m-%d %H:%M:%S'):
    """Formate une date et heure dans le format spécifié"""
    if not dt:
        return ""
    # S'assurer que la date est dans le fuseau horaire de Paris
    if dt.tzinfo is not None:
        dt = utc_to_paris(dt)
    return dt.strftime(format_str)

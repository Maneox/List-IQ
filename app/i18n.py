from flask import request, session, g, Blueprint, redirect, url_for
from flask_babel import Babel, gettext, lazy_gettext
import os

# Créer un blueprint pour les routes liées à l'internationalisation
i18n_bp = Blueprint('i18n', __name__)

# Initialisation de l'extension Babel
babel = Babel()

def get_locale():
    """
    Détermine la langue à utiliser pour l'utilisateur actuel.
    Ordre de priorité :
    1. Langue choisie par l'utilisateur et stockée en session
    2. Langue préférée du navigateur si supportée
    3. Langue par défaut définie dans .env
    """
    # Si l'utilisateur a explicitement choisi une langue, on l'utilise
    if 'language' in session:
        return session['language']
    
    # Sinon, on essaie de détecter la langue du navigateur
    # Langues supportées par l'application
    supported_languages = ['fr', 'en']
    
    # Récupérer la meilleure correspondance entre les langues demandées par le navigateur
    # et les langues supportées par l'application
    best_match = request.accept_languages.best_match(supported_languages)
    
    # Si une correspondance est trouvée, on l'utilise
    if best_match:
        return best_match
    
    # Sinon, on utilise la langue par défaut définie dans .env ou 'fr' par défaut
    return os.getenv('DEFAULT_LANGUAGE', 'fr')

def init_app(app):
    """
    Initialise l'extension Babel avec l'application Flask.
    """
    # Configuration de Babel
    app.config['BABEL_DEFAULT_LOCALE'] = os.getenv('DEFAULT_LANGUAGE', 'fr')
    app.config['BABEL_DEFAULT_TIMEZONE'] = 'Europe/Paris'
    app.config['BABEL_TRANSLATION_DIRECTORIES'] = 'translations'
    
    # Initialiser Babel avec la fonction de sélection de locale
    babel.init_app(app, locale_selector=get_locale)
    
    # Ajouter gettext et lazy_gettext comme fonctions globales pour les templates
    app.jinja_env.globals['gettext'] = gettext
    app.jinja_env.globals['_'] = gettext
    app.jinja_env.globals['lazy_gettext'] = lazy_gettext
    
    # Enregistrer le blueprint pour les routes d'internationalisation
    app.register_blueprint(i18n_bp)

# Route pour changer la langue
@i18n_bp.route('/set_language/<language>')
def set_language(language):
    """
    Change la langue de l'interface pour l'utilisateur actuel.
    La langue est stockée en session.
    """
    # Vérifier que la langue demandée est supportée
    if language in ['fr', 'en']:
        session['language'] = language
        
        # Si l'utilisateur vient d'une page, on le redirige vers cette page
        next_url = request.args.get('next') or request.referrer or '/'
        return redirect(next_url)
    
    # Si la langue n'est pas supportée, on reste sur la page actuelle
    return redirect(request.referrer or '/')

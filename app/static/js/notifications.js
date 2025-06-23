/**
 * Système de notifications temporaires
 * Remplace les alertes standard par des notifications élégantes qui disparaissent automatiquement
 */

// Fonction pour afficher une notification temporaire
function showNotification(message, type = 'success', duration = 3000) {
    console.log(`Affichage d'une notification ${type}: ${message}`);
    
    // Créer l'élément de notification
    const notification = document.createElement('div');
    notification.className = `alert alert-${type} alert-dismissible fade show`;
    notification.role = 'alert';
    notification.style.marginBottom = '10px';
    notification.style.boxShadow = '0 4px 8px rgba(0, 0, 0, 0.1)';
    
    // Ajouter le message
    notification.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
    `;
    
    // Ajouter la notification au conteneur
    const container = document.getElementById('notificationContainer');
    if (container) {
        container.appendChild(notification);
        
        // Créer une instance d'alerte Bootstrap pour pouvoir la fermer programmatiquement
        const bsAlert = new bootstrap.Alert(notification);
        
        // Programmer la fermeture automatique
        setTimeout(() => {
            bsAlert.close();
        }, duration);
        
        // Supprimer l'élément après la fermeture
        notification.addEventListener('closed.bs.alert', function() {
            if (notification.parentNode) {
                notification.parentNode.removeChild(notification);
            }
        });
    } else {
        console.error('Conteneur de notifications non trouvé');
        // Fallback à l'alerte standard si le conteneur n'est pas trouvé
        alert(message);
    }
}

// Fonction pour afficher une notification de succès
function showSuccess(message, duration = 3000) {
    showNotification(message, 'success', duration);
}

// Fonction pour afficher une notification d'erreur
function showError(message, duration = 5000) {
    showNotification(message, 'danger', duration);
}

// Fonction pour afficher une notification d'avertissement
function showWarning(message, duration = 4000) {
    showNotification(message, 'warning', duration);
}

// Fonction pour afficher une notification d'information
function showInfo(message, duration = 3000) {
    showNotification(message, 'info', duration);
}

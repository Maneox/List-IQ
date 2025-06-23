/**
 * Fonctions JavaScript pour la gestion des utilisateurs
 */

// Fonction pour supprimer un utilisateur
function deleteUser(userId, username) {
    if (confirm(`Êtes-vous sûr de vouloir supprimer l'utilisateur "${username}" ?`)) {
        console.log(`Tentative de suppression de l'utilisateur ${username} (ID: ${userId})`);
        
        // Utiliser le formulaire caché avec le token CSRF déjà inclus
        const form = document.getElementById(`delete-form-${userId}`);
        
        if (form) {
            console.log('Formulaire de suppression trouvé, soumission...');
            form.submit();
        } else {
            console.error(`Formulaire de suppression non trouvé pour l'utilisateur ${userId}`);
            alert(`Erreur: Impossible de trouver le formulaire de suppression pour l'utilisateur ${username}`);
        }
    }
}

// Fonction pour initialiser les gestionnaires d'événements
function initDeleteButtons() {
    console.log('Initialisation des boutons de suppression');
    
    // D'abord, supprimer tous les gestionnaires d'événements existants
    // pour éviter les doublons
    const deleteButtons = document.querySelectorAll('.delete-user-btn');
    deleteButtons.forEach(button => {
        // Utiliser une copie du bouton pour supprimer tous les gestionnaires
        const newButton = button.cloneNode(true);
        button.parentNode.replaceChild(newButton, button);
    });
    
    // Récupérer les nouveaux boutons après le remplacement
    const newDeleteButtons = document.querySelectorAll('.delete-user-btn');
    console.log(`Nombre de boutons de suppression trouvés: ${newDeleteButtons.length}`);
    
    // Ajouter des gestionnaires d'événements pour les boutons de suppression
    newDeleteButtons.forEach(button => {
        console.log('Ajout d\'un gestionnaire d\'événement pour le bouton');
        
        button.addEventListener('click', function(event) {
            // Empêcher les clics multiples
            event.preventDefault();
            if (this.disabled) return;
            this.disabled = true;
            
            console.log('Bouton de suppression cliqué');
            const userId = this.getAttribute('data-user-id');
            const username = this.getAttribute('data-username');
            console.log(`Suppression de l'utilisateur: ${username} (ID: ${userId})`);
            deleteUser(userId, username);
        });
    });
}

// Initialisation des événements lorsque le DOM est chargé
document.addEventListener('DOMContentLoaded', function() {
    console.log('Module de gestion des utilisateurs chargé');
    initDeleteButtons();
});

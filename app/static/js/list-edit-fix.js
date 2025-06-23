/**
 * Correctif pour permettre l'édition immédiate des nouvelles lignes ajoutées
 * Ce script remplace la fonction initializeEditButtons pour supprimer la vérification
 * qui empêche la réinitialisation des gestionnaires d'événements
 */
document.addEventListener('DOMContentLoaded', function() {
    console.log('Correctif pour l\'édition des nouvelles lignes chargé');
    
    // Remplacer la fonction initializeEditButtons existante
    window.initializeEditButtons = function() {
        console.log('Initialisation/réinitialisation des boutons d\'édition (version corrigée)');
        
        // Ajouter des gestionnaires d'événements pour les boutons d'édition
        document.querySelectorAll('.edit-row-btn').forEach(button => {
            // Supprimer d'abord les gestionnaires existants pour éviter les doublons
            button.removeEventListener('click', handleEditButtonClick);
            
            // Ajouter le nouveau gestionnaire
            button.addEventListener('click', handleEditButtonClick);
        });
    };
    
    // Fonction de gestion du clic sur le bouton d'édition
    function handleEditButtonClick() {
        const rowId = this.getAttribute('data-row-id');
        const rowDataStr = this.getAttribute('data-row-data');
        console.log('Clic sur le bouton d\'édition pour la ligne:', rowId);
        console.log('Données brutes:', rowDataStr);
        
        try {
            // Convertir la chaîne JSON en objet JavaScript
            const rowData = JSON.parse(rowDataStr);
            console.log('Données parsées:', rowData);
            
            // Appeler la fonction editRow
            editRow(rowId, rowData);
        } catch (error) {
            console.error('Erreur lors du parsing des données:', error);
        }
    }
    
    // Appliquer le correctif après un court délai pour s'assurer que le script original est chargé
    setTimeout(function() {
        // Réinitialiser les boutons d'édition avec la nouvelle fonction
        initializeEditButtons();
        console.log('Correctif appliqué avec succès');
    }, 500);
});

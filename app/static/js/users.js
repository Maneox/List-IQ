/**
 * JavaScript functions for user management.
 * NOTE: This file is prepared for i18n extraction.
 * It uses window.translations and window._() from translations.js
 */

// Function to delete a user
function deleteUser(userId, username) {
    // The user-facing string is wrapped for translation.
    // Debug the translation
    console.log('Translation key:', 'Are you sure you want to delete user');
    console.log('Translation value:', window.translations["Are you sure you want to delete user"]);
    console.log('window._ result:', window._("Are you sure you want to delete user"));
    
    if (confirm(window._("Are you sure you want to delete user") + (" "+username+" ?"))){
        
        // Use the hidden form with the CSRF token already included
        const form = document.getElementById(`delete-form-${userId}`);
        
        if (form) {
            console.log('Delete form found, submitting...');
            form.submit();
        } else {
            console.error(`Delete form not found for user ${userId}`);
            // The user-facing alert is also wrapped for translation.
            alert(window.interpolate(window._("Error: Could not find the delete form for user %s"), [username]));
        }
    }
}

// Function to initialize event handlers
function initDeleteButtons() {
    console.log('Initializing delete buttons');
    
    // First, remove all existing event handlers to avoid duplicates
    const deleteButtons = document.querySelectorAll('.delete-user-btn');
    deleteButtons.forEach(button => {
        // Use a copy of the button to remove all handlers
        const newButton = button.cloneNode(true);
        button.parentNode.replaceChild(newButton, button);
    });
    
    // Get the new buttons after replacement
    const newDeleteButtons = document.querySelectorAll('.delete-user-btn');
    console.log(`Number of delete buttons found: ${newDeleteButtons.length}`);
    
    // Add event handlers for the delete buttons
    newDeleteButtons.forEach(button => {
        console.log('Adding an event handler for the button');
        
        button.addEventListener('click', function(event) {
            // Prevent multiple clicks
            event.preventDefault();
            if (this.disabled) return;
            this.disabled = true;
            
            console.log('Delete button clicked');
            const userId = this.getAttribute('data-user-id');
            const username = this.getAttribute('data-username');
            console.log(`Deleting user: ${username} (ID: ${userId})`);
            deleteUser(userId, username);
        });
    });
}

// Initialize events when the DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    console.log('User management module loaded');
    initDeleteButtons();
});
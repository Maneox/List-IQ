/**
 * JavaScript functions for user management
 */

// Function to delete a user
function deleteUser(userId, username) {
    if (confirm(t('users.delete_confirm', { username: username }))) {
        console.log(t('users.attempting_delete', { username: username, userId: userId }));
        
        // Use the hidden form with the CSRF token already included
        const form = document.getElementById(`delete-form-${userId}`);
        
        if (form) {
            console.log(t('users.delete_form_found'));
            form.submit();
        } else {
            console.error(t('users.delete_error_form', { username: username }));
            alert(t('users.delete_error'));
        }
    }
}

// Function to initialize event handlers
function initDeleteButtons() {
    console.log('Initializing delete buttons');
    
    // First, remove all existing event handlers
    // to avoid duplicates
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
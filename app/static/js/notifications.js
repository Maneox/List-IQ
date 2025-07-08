/**
 * Temporary notification system
<<<<<<< HEAD
 * Replaces standard alerts with elegant, auto-dismissing notifications
=======
 * Replaces standard alerts with elegant, auto-dismissing notifications.
 * NOTE: This file is prepared for i18n extraction.
 * It assumes the existence of a global function `_()`.
>>>>>>> origin/pybabel_update
 */

// Function to display a temporary notification
function showNotification(message, type = 'success', duration = 3000) {
    console.log(`Displaying a ${type} notification: ${message}`);
<<<<<<< HEAD
    
=======

>>>>>>> origin/pybabel_update
    // Create the notification element
    const notification = document.createElement('div');
    notification.className = `alert alert-${type} alert-dismissible fade show`;
    notification.role = 'alert';
    notification.style.marginBottom = '10px';
    notification.style.boxShadow = '0 4px 8px rgba(0, 0, 0, 0.1)';
<<<<<<< HEAD
    
=======

>>>>>>> origin/pybabel_update
    // Add the message
    notification.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
    `;
<<<<<<< HEAD
    
=======

>>>>>>> origin/pybabel_update
    // Add the notification to the container
    const container = document.getElementById('notificationContainer');
    if (container) {
        container.appendChild(notification);
<<<<<<< HEAD
        
        // Create a Bootstrap alert instance to be able to close it programmatically
        const bsAlert = new bootstrap.Alert(notification);
        
=======

        // Create a Bootstrap alert instance to be able to close it programmatically
        const bsAlert = new bootstrap.Alert(notification);

>>>>>>> origin/pybabel_update
        // Schedule automatic closing
        setTimeout(() => {
            bsAlert.close();
        }, duration);
<<<<<<< HEAD
        
        // Remove the element after closing
=======

        // Remove the element after it's closed
>>>>>>> origin/pybabel_update
        notification.addEventListener('closed.bs.alert', function() {
            if (notification.parentNode) {
                notification.parentNode.removeChild(notification);
            }
        });
    } else {
        console.error('Notification container not found');
<<<<<<< HEAD
        // Fallback to the standard alert if the container is not found
        alert(message);
=======
        // Fallback to a standard alert if the container is not found
        // The message passed to alert is expected to be already translated where it's called.
        // We wrap it here just in case a raw string is ever passed.
        alert(_(message));
>>>>>>> origin/pybabel_update
    }
}

// Function to display a success notification
function showSuccess(message, duration = 3000) {
    showNotification(message, 'success', duration);
}

// Function to display an error notification
function showError(message, duration = 5000) {
    showNotification(message, 'danger', duration);
}

// Function to display a warning notification
function showWarning(message, duration = 4000) {
    showNotification(message, 'warning', duration);
}

<<<<<<< HEAD
// Function to display an info notification
=======
// Function to display an information notification
>>>>>>> origin/pybabel_update
function showInfo(message, duration = 3000) {
    showNotification(message, 'info', duration);
}
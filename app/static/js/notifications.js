/**
 * Temporary notification system
 * Replaces standard alerts with elegant, auto-dismissing notifications.
 * NOTE: This file is prepared for i18n extraction.
 * It assumes the existence of a global function `_()`.
 */

// Function to display a temporary notification
function showNotification(message, type = 'success', duration = 3000) {
    console.log(`Displaying a ${type} notification: ${message}`);

    // Create the notification element
    const notification = document.createElement('div');
    notification.className = `alert alert-${type} alert-dismissible fade show`;
    notification.role = 'alert';
    notification.style.marginBottom = '10px';
    notification.style.boxShadow = '0 4px 8px rgba(0, 0, 0, 0.1)';

    // Add the message
    notification.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
    `;

    // Add the notification to the container
    const container = document.getElementById('notificationContainer');
    if (container) {
        container.appendChild(notification);

        // Create a Bootstrap alert instance to be able to close it programmatically
        const bsAlert = new bootstrap.Alert(notification);

        // Schedule automatic closing
        setTimeout(() => {
            bsAlert.close();
        }, duration);

        // Remove the element after it's closed
        notification.addEventListener('closed.bs.alert', function() {
            if (notification.parentNode) {
                notification.parentNode.removeChild(notification);
            }
        });
    } else {
        console.error('Notification container not found');
        // Fallback to a standard alert if the container is not found
        // The message passed to alert is expected to be already translated where it's called.
        // We wrap it here just in case a raw string is ever passed.
        alert(_(message));
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

// Function to display an information notification
function showInfo(message, duration = 3000) {
    showNotification(message, 'info', duration);
}
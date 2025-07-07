/**
 * Fix to allow immediate editing of newly added rows.
 * This script replaces the initializeEditButtons function to remove the check
 * that prevents re-initializing event handlers.
 */
document.addEventListener('DOMContentLoaded', function() {
    console.log('Patch for new row editing loaded');

    // Replace the existing initializeEditButtons function
    window.initializeEditButtons = function() {
        console.log('Initializing/re-initializing edit buttons (patched version)');

        // Add event handlers for the edit buttons
        document.querySelectorAll('.edit-row-btn').forEach(button => {
            // First, remove existing handlers to avoid duplicates
            button.removeEventListener('click', handleEditButtonClick);

            // Add the new handler
            button.addEventListener('click', handleEditButtonClick);
        });
    };

    // Handler function for the edit button click
    function handleEditButtonClick() {
        const rowId = this.getAttribute('data-row-id');
        const rowDataStr = this.getAttribute('data-row-data');
        console.log('Edit button clicked for row:', rowId);
        console.log('Raw data:', rowDataStr);

        try {
            // Convert the JSON string to a JavaScript object
            const rowData = JSON.parse(rowDataStr);
            console.log('Parsed data:', rowData);

            // Call the editRow function
            editRow(rowId, rowData);
        } catch (error) {
            console.error('Error parsing data:', error);
        }
    }

    // Apply the patch after a short delay to ensure the original script has loaded
    setTimeout(function() {
        // Re-initialize the edit buttons with the new function
        initializeEditButtons();
        console.log('Patch applied successfully');
    }, 500);
});
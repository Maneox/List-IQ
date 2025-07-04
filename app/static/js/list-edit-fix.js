/**
 * Fix to allow immediate editing of newly added rows.
 * This script replaces the initializeEditButtons function to remove the check
 * that prevents re-initialization of event handlers.
 */
document.addEventListener('DOMContentLoaded', function() {
    console.log('Fix for editing new rows loaded');
    
    // Replace the existing initializeEditButtons function
    window.initializeEditButtons = function() {
        console.log('Initializing/re-initializing edit buttons (fixed version)');
        
        // Add event handlers for edit buttons
        document.querySelectorAll('.edit-row-btn').forEach(button => {
            // First, remove existing handlers to avoid duplicates
            button.removeEventListener('click', handleEditButtonClick);
            
            // Add the new handler
            button.addEventListener('click', handleEditButtonClick);
        });
    };
    
    // Function to handle the click on the edit button
    function handleEditButtonClick() {
        const rowId = this.getAttribute('data-row-id');
        const rowDataStr = this.getAttribute('data-row-data');
        console.log('Click on edit button for row:', rowId);
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
    
    // Apply the fix after a short delay to ensure the original script is loaded
    setTimeout(function() {
        // Re-initialize edit buttons with the new function
        initializeEditButtons();
        console.log('Fix applied successfully');
    }, 500);
});
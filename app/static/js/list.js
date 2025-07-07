// Variable to prevent multiple calls to deleteSelectedRows
let deleteInProgress = false;

// Function to delete selected rows
function deleteSelectedRows() {
    console.log('%c=== Start of deleteSelectedRows function ===', 'background: #222; color: #bada55');
    
    // Check if a deletion is already in progress
    if (deleteInProgress) {
        console.log('A deletion is already in progress, cancelling this call');
        return;
    }
    
    // Get all selected checkboxes with the exact selector
    const selectedCheckboxes = document.querySelectorAll('#dataTable tbody .row-checkbox:checked');
    console.log('Number of selected checkboxes:', selectedCheckboxes.length);
    const selectedCount = selectedCheckboxes.length;
    
    if (selectedCount === 0) {
        alert(_('No rows selected'));
        return;
    }
    
    // Mark that the deletion is in progress
    deleteInProgress = true;
    
    // Ask for confirmation once for all rows
    if (!confirm(interpolate(_('Are you sure you want to delete %s row(s)?'), [selectedCount]))) {
        // Reset state if user cancels
        deleteInProgress = false;
        return;
    }
    
    // Get the DataTables instance
    const dataTable = $('#dataTable').DataTable();
    
    // Get the IDs of the rows to delete
    const rowIds = [];
    selectedCheckboxes.forEach(checkbox => {
        // Get the row ID from the data-row-id attribute
        const rowId = checkbox.getAttribute('data-row-id');
        if (rowId) {
            rowIds.push(parseInt(rowId));
        } else {
            // If data-row-id is not available on the checkbox, try to get it from the row
            const row = checkbox.closest('tr');
            if (row && row.getAttribute('data-row-id')) {
                rowIds.push(parseInt(row.getAttribute('data-row-id')));
            }
        }
    });
    
    console.log('IDs of rows to delete:', rowIds);
    
    if (rowIds.length === 0) {
        alert(_('No valid row IDs found'));
        return;
    }
    
    // Get the CSRF token
    const csrfMetaTag = document.querySelector('meta[name="csrf-token"]');
    if (!csrfMetaTag) {
        console.error('CSRF token not found');
        alert(_('Error: Missing CSRF token'));
        return;
    }
    
    const csrfToken = csrfMetaTag.getAttribute('content');
    
    // Get the list ID from the hidden element (preferred method)
    const listIdInput = document.getElementById('listId');
    if (listIdInput && listIdInput.value) {
        const listId = parseInt(listIdInput.value);
        if (!isNaN(listId)) {
            console.log('List ID retrieved from hidden element:', listId);
            // Send the request with the retrieved ID
            performDeleteRequest(listId, rowIds, csrfToken, dataTable, selectedCheckboxes, selectedCount);
            return;
        }
    }
    
    // If the ID is not available in the hidden element, try to get it from the URL
    const pathParts = window.location.pathname.split('/');
    const listsIndex = pathParts.indexOf('lists');
    
    if (listsIndex !== -1 && listsIndex + 1 < pathParts.length) {
        const potentialId = pathParts[listsIndex + 1];
        if (potentialId && !isNaN(parseInt(potentialId))) {
            const listId = parseInt(potentialId);
            console.log('List ID extracted from URL:', listId);
            performDeleteRequest(listId, rowIds, csrfToken, dataTable, selectedCheckboxes, selectedCount);
            return;
        }
    }
    
    // If we get here, it means we couldn't retrieve the list ID
    console.error('List ID not found');
    alert(_('Error: Missing list ID'));
}

// Function to perform the delete request
function performDeleteRequest(listId, rowIds, csrfToken, dataTable, selectedCheckboxes, selectedCount) {
    console.log('%c=== Start of performDeleteRequest function ===', 'background: #222; color: #bada55');
    console.log('Sending delete request for list:', listId, 'with rows:', rowIds);
    
    // Disable the delete button during processing
    const deleteSelectedBtn = document.getElementById('deleteSelectedBtn');
    if (deleteSelectedBtn) {
        deleteSelectedBtn.disabled = true;
        deleteSelectedBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> ' + _('Deleting...');
    }
    
    // Build the URL with the exact format expected by the backend
    const deleteUrl = `/api/lists/${listId}/data/bulk-delete`;
    
    // Send the delete request
    fetch(deleteUrl, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRF-Token': csrfToken
        },
        body: JSON.stringify({
            row_ids: rowIds
        }),
        credentials: 'same-origin'
    })
    .then(response => {
        console.log('Response status:', response.status);
        // Even if the response is not OK (404, etc.), we still want to parse the JSON
        // to get the error message
        return response.json().catch(e => {
            // If we can't parse the JSON, throw an error with the HTTP status
            throw new Error(`HTTP Error ${response.status}`);
        }).then(data => {
            // If the response is not OK, add the HTTP status to the data
            if (!response.ok) {
                data.httpStatus = response.status;
            }
            return data;
        });
    })
    .then(data => {
        console.log('Response data:', data);
        
        // Re-enable the delete button
        if (deleteSelectedBtn) {
            deleteSelectedBtn.disabled = false;
            deleteSelectedBtn.innerHTML = `<i class="fas fa-trash"></i> ` + _('Delete selection');
            deleteSelectedBtn.style.display = 'none'; // Hide the button after deletion
        }
        
        // Explicitly check the success field
        if (data.success === true) {
            console.log('Deletion successful!');
            
            // Remove the rows from the table
            selectedCheckboxes.forEach(checkbox => {
                const row = checkbox.closest('tr');
                if (row) {
                    dataTable.row(row).remove();
                }
            });
            
            // Redraw the table
            dataTable.draw();
            
            // Reset checkboxes
            resetCheckboxes();
            
            // Display a success message
            const successMessage = data.message || interpolate(_('%s row(s) deleted successfully'), [data.deleted_count]);
            alert(successMessage);
        } else {
            // The request failed or no rows were deleted
            const errorMessage = data.error || _('No rows could be deleted');
            console.error('Deletion error:', errorMessage);
            alert(_('Error during deletion: ') + errorMessage);
        }
    })
    .catch(error => {
        console.error('Error during deletion:', error);
        
        // Re-enable the delete button
        if (deleteSelectedBtn) {
            deleteSelectedBtn.disabled = false;
            deleteSelectedBtn.innerHTML = `<i class="fas fa-trash"></i> ` + _('Delete selection');
        }
        
        alert(_('Error during deletion: ') + error.message);
    })
    .finally(() => {
        // Reset the deletion state
        deleteInProgress = false;
    });
}

// Variable to track if multiple selection has been set up
let multipleSelectionInitialized = false;

// Function to handle multiple row selection
function setupMultipleSelection() {
    // Check if multiple selection has already been set up
    if (multipleSelectionInitialized) {
        console.log('Multiple selection has already been set up, skipping this initialization');
        return;
    }
    
    console.log('Setting up multiple selection');
    
    const selectAllCheckbox = document.getElementById('selectAll');
    const deleteSelectedBtn = document.getElementById('deleteSelectedBtn');
    const dataTable = document.getElementById('dataTable');
    let dataTableApi = null;
    
    // Initialize DataTables API if it exists
    if (dataTable && $.fn.DataTable.isDataTable('#dataTable')) {
        dataTableApi = $(dataTable).DataTable();
    }

    // Function to update the delete button's visibility
    function updateDeleteButtonVisibility() {
        const selectedCount = document.querySelectorAll('#dataTable tbody .row-checkbox:checked').length;
        if (selectedCount > 0) {
            deleteSelectedBtn.style.display = 'inline-block';
            deleteSelectedBtn.textContent = interpolate(_('Delete (%s)'), [selectedCount]);
        } else {
            deleteSelectedBtn.style.display = 'none';
        }
    }

    // Handler for the "Select All" checkbox
    if (selectAllCheckbox) {
        // Use jQuery to handle the change event
        $(selectAllCheckbox).off('change').on('change', function() {
            const isChecked = this.checked;
            
            // Use DataTables API to select all visible checkboxes
            const table = $('#dataTable').DataTable();
            
            // Select only the checkboxes of the currently visible rows in the DOM
            $('#dataTable tbody tr:visible .row-checkbox').prop('checked', isChecked);
            
            // Update the delete button's visibility
            updateDeleteButtonVisibility();
        });
    }

    // Use event delegation with jQuery for row checkboxes
    $(document).off('change', '.row-checkbox').on('change', '.row-checkbox', function() {
        // Update the delete button's visibility
        updateDeleteButtonVisibility();
        
        // Update the "Select All" checkbox
        if (selectAllCheckbox) {
            const totalCheckboxes = $('.row-checkbox').length;
            const checkedCheckboxes = $('.row-checkbox:checked').length;
            
            // Update the state of the "Select All" checkbox
            selectAllCheckbox.checked = (totalCheckboxes > 0 && totalCheckboxes === checkedCheckboxes);
        }
    });

    // Handler for the multiple delete button
    if (deleteSelectedBtn) {
        // Remove all existing event handlers
        $(deleteSelectedBtn).off('click');
        
        // Add a single event handler
        $(deleteSelectedBtn).on('click', function(e) {
            // Prevent default behavior and propagation
            e.preventDefault();
            e.stopPropagation();
            
            console.log('%c=== Click on multiple delete button ===', 'background: #222; color: #bada55');
            // Call the multiple delete function
            deleteSelectedRows();
        });
    }
    
    // Mark multiple selection as set up
    multipleSelectionInitialized = true;
}

// Variable to prevent multiple submissions of the import form
let importInProgress = false;

// Function to import data
function submitImport(event) {
    event.preventDefault();
    console.log('submitImport function called');
    
    // Check if an import is already in progress
    if (importInProgress) {
        console.log('An import is already in progress, cancelling this call');
        return;
    }
    
    // Mark that the import is in progress
    importInProgress = true;
    
    const form = event.target;
    const submitButton = form.querySelector('button[type="submit"]');
    const formData = new FormData(form);

    submitButton.disabled = true;
    submitButton.textContent = _('Importing...');

    console.log('Sending import request...');
    console.log('FormData:', Array.from(formData.entries()));

    // Get the CSRF token
    const csrfMetaTag = document.querySelector('meta[name="csrf-token"]');
    if (!csrfMetaTag) {
        console.error('CSRF token not found');
        alert(_('Error: Missing CSRF token'));
        submitButton.disabled = false;
        submitButton.textContent = _('Import');
        return;
    }
    
    const csrfToken = csrfMetaTag.getAttribute('content');

    // Request configuration
    const requestOptions = {
        method: 'POST',
        headers: {
            'X-CSRFToken': csrfToken
        },
        body: formData,
        credentials: 'same-origin'
    };
    
    console.log('Request options:', requestOptions);

    fetch(`/api/lists/${listId}/import`, requestOptions)
    .then(response => {
        console.log('Response received:', response);
        return response.json().then(data => {
            if (!response.ok) {
                throw new Error(data.error || _('Error during import'));
            }
            return data;
        });
    })
    .then(data => {
        console.log('Data received:', data);
        if (data.message) {
            // Close the modal
            const modal = bootstrap.Modal.getInstance(document.getElementById('importModal'));
            modal.hide();
            // Reload the page
            window.location.reload();
        } else {
            throw new Error(data.error || _('Error during import'));
        }
    })
    .catch(error => {
        console.error('Error:', error);
        alert(error.message || _('Error during import'));
    })
    .finally(() => {
        // Re-enable the button
        submitButton.disabled = false;
        submitButton.textContent = _('Import');
        // Reset the import state
        importInProgress = false;
        console.log('Import finished, resetting importInProgress');
    });
}

// Function to add a row
function submitAddRow(event) {
    event.preventDefault();
    
    // Prevent double submission
    const form = event.target;
    if (form.dataset.submitting === 'true') {
        console.log('Form already submitting');
        return;
    }
    form.dataset.submitting = 'true';
    
    console.log('Submitting add form');

    // Get the form and button
    const submitButton = form.querySelector('button[type="submit"]');

    // Get form data
    const formData = new FormData(form);
    const data = {};
    
    // Get all form fields and their types
    const inputs = form.querySelectorAll('input, select, textarea');
    
    // Loop through all fields to collect data with the correct type
    inputs.forEach(input => {
        if (!input.name || input.name === '') return;
        
        let value = input.value.trim();
        
        // Ignore empty fields
        if (value === '') {
            data[input.name] = '';
            return;
        }
        
        // Special handling based on field type
        if (input.classList.contains('datepicker')) {
            // For dates, ensure they are in DD/MM/YYYY format
            if (input._flatpickr) {
                const dateObj = input._flatpickr.selectedDates[0];
                if (dateObj) {
                    const day = dateObj.getDate().toString().padStart(2, '0');
                    const month = (dateObj.getMonth() + 1).toString().padStart(2, '0');
                    const year = dateObj.getFullYear();
                    value = `${day}/${month}/${year}`;
                }
            }
        } else if (input.type === 'number') {
            // For numbers, convert to number
            value = value !== '' ? Number(value) : '';
        }
        
        data[input.name] = value;
    });

    console.log('Data to send:', data);

    // Get the CSRF token
    const csrfMetaTag = document.querySelector('meta[name="csrf-token"]');
    if (!csrfMetaTag) {
        console.error('CSRF token not found');
        alert(_('Error: Missing CSRF token'));
        form.dataset.submitting = 'false';
        return;
    }
    
    const csrfToken = csrfMetaTag.getAttribute('content');

    // Get the list ID
    const listIdElement = document.getElementById('listId');
    const currentListId = listIdElement ? listIdElement.value : listId;
    
    if (!currentListId) {
        console.error('List ID not found');
        alert(_('Error: Missing list ID'));
        form.dataset.submitting = 'false';
        return;
    }
    
    console.log('List ID used for adding:', currentListId);

    // Disable the button
    submitButton.disabled = true;
    submitButton.innerHTML = '<i class="fas fa-spinner fa-spin"></i> ' + _('Adding...');

    let newRowId = null;

    // Request configuration
    const requestOptions = {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'X-Requested-With': 'XMLHttpRequest',
            'X-CSRF-Token': csrfToken
        },
        body: JSON.stringify(data),
        credentials: 'same-origin'
    };

    // Exact API URL
    const apiUrl = `/api/lists/${currentListId}/data`;
    console.log('API URL:', apiUrl);

    // Send the data
    fetch(apiUrl, requestOptions)
    .then(response => {
        console.log('Response status:', response.status);
        // Even if the response is not OK, we still want to parse the JSON
        return response.json().catch(e => {
            // If we can't parse the JSON, throw an error with the HTTP status
            throw new Error(`HTTP Error ${response.status}`);
        }).then(data => {
            // If the response is not OK, add the HTTP status to the data and throw an error
            if (!response.ok) {
                const errorMsg = data.error || interpolate(_('Error during add (%s)'), [response.status]);
                throw new Error(errorMsg);
            }
            return data;
        });
    })
    .then(data => {
        console.log('Data received after add:', data);
        if (!data.message || !data.row_id) {
            throw new Error(_('Invalid server response'));
        }
        
        newRowId = data.row_id;
        
        // Close the modal
        const modal = bootstrap.Modal.getInstance(document.getElementById('addRowModal'));
        if (modal) {
            modal.hide();
        }

        // Reset the form
        form.reset();

        // Wait a bit before fetching data to ensure it's saved
        return new Promise(resolve => setTimeout(resolve, 300))
            .then(() => fetch(`/api/lists/${currentListId}/data/${newRowId}`));
    })
    .then(response => {
        if (!response.ok) {
            throw new Error(_('Error fetching row data'));
        }
        return response.json();
    })
    .then(rowData => {
        console.log('Row data received:', rowData);
        
        if (!rowData || !rowData.data) {
            throw new Error(_('Row data is invalid'));
        }

        // Add the new row to the table using the DataTables API
        const dataTable = $('#dataTable').DataTable();
        
        // Prepare the data for DataTables
        const rowDataArray = [];
        
        // Check if the first column is a checkbox
        const hasCheckbox = document.querySelector('#dataTable thead th input[type="checkbox"]') !== null;
        
        // Add the checkbox as the first cell if needed
        if (hasCheckbox) {
            rowDataArray.push(`<input type="checkbox" class="row-checkbox" data-row-id="${rowData.row_id}">`);
        }
        
        // Get the column order from the table headers
        const headers = Array.from(document.querySelectorAll('#dataTable thead th'));
        // Exclude the first (checkbox) and last (actions) columns if they exist
        const startIndex = hasCheckbox ? 1 : 0;
        const endIndex = document.querySelector('#dataTable thead th:last-child').textContent.trim() === 'Actions' ? -1 : undefined;
        const dataHeaders = headers.slice(startIndex, endIndex);
        
        // Add data cells in column order
        dataHeaders.forEach(header => {
            const columnName = header.textContent.trim();
            rowDataArray.push(rowData.data[columnName] || '');
        });
        
        // Add action buttons as the last cell if the Actions column exists
        if (endIndex === -1) {
            rowDataArray.push(`
                <button type="button" class="btn btn-sm btn-primary edit-row-btn" data-row-id="${rowData.row_id}" data-row-data='${JSON.stringify(rowData.data)}'>
                    <i class="fas fa-edit"></i>
                </button>
                <button type="button" class="btn btn-sm btn-danger" onclick="deleteRow('${rowData.row_id}')">
                    <i class="fas fa-trash"></i>
                </button>
            `);
        }
        
        // Add the row to DataTables
        const newRowNode = dataTable.row.add(rowDataArray).draw().node();
        
        // Add the data-row-id attribute to the row
        $(newRowNode).attr('data-row-id', rowData.row_id);
        
        // Re-initialize event handlers for edit buttons
        initializeEditButtons();
        
        console.log('Row added successfully via DataTables API');
        
        // Display a temporary success notification
        if (typeof showSuccess === 'function') {
            showSuccess(_('Row added successfully'));
        } else {
            console.log('showSuccess function not available');
        }
    })
    .catch(error => {
        console.error('Error:', error);
        alert(error.message || _('Error during add'));
    })
    .finally(() => {
        // Re-enable the button and form
        submitButton.disabled = false;
        submitButton.innerHTML = _('Add');
        form.dataset.submitting = 'false';
    });
}

// Variable to track if event handlers have been initialized
let editButtonsInitialized = false;

// Function to initialize edit buttons - extracted to avoid multiple initializations
function initializeEditButtons() {
    // Check if buttons have already been initialized
    if (editButtonsInitialized) {
        console.log('Edit buttons have already been initialized, skipping this initialization');
        return;
    }
    
    console.log('Initializing edit buttons');
    
    // Add event handlers for edit buttons
    document.querySelectorAll('.edit-row-btn').forEach(button => {
        console.log('Adding a handler for the edit button:', button);
        button.addEventListener('click', function() {
            const rowId = this.getAttribute('data-row-id');
            const rowDataStr = this.getAttribute('data-row-data');
            console.log('Click on edit button for row:', rowId);
            console.log('Raw data:', rowDataStr);
            
            try {
                // Convert JSON string to JavaScript object
                const rowData = JSON.parse(rowDataStr);
                console.log('Parsed data:', rowData);
                
                // Call the editRow function
                editRow(rowId, rowData);
            } catch (error) {
                console.error('Error while parsing data:', error);
            }
        });
    });
    
    // Add an event handler for the cancel button of the edit modal
    const cancelEditButton = document.querySelector('#editRowModal .btn-secondary[data-bs-dismiss="modal"]');
    if (cancelEditButton) {
        console.log('Adding a handler for the cancel button of the edit modal');
        cancelEditButton.addEventListener('click', function() {
            // Ensure the backdrop is removed
            setTimeout(() => {
                // Manually remove the modal-backdrop class and overflow style
                const backdrop = document.querySelector('.modal-backdrop');
                if (backdrop) {
                    backdrop.remove();
                }
                // Restore normal page scrolling
                document.body.classList.remove('modal-open');
                document.body.style.overflow = '';
                document.body.style.paddingRight = '';
            }, 300);
        });
    }
    
    // Mark buttons as initialized
    editButtonsInitialized = true;
}

// Add an event listener to initialize handlers on page load
document.addEventListener('DOMContentLoaded', function() {
    console.log('Page loaded, initializing event handlers');
    
    // Initialize edit buttons
    initializeEditButtons();
});

// Function to edit a row
function editRow(rowId, rowData) {
    console.log('%c=== Start of editRow function ===', 'background: #222; color: #bada55');
    console.log('Editing row:', rowId);
    console.log('Type of rowData:', typeof rowData);
    console.log('Row data:', rowData);
    
    // Function called with rowId
    console.log('editRow function called with rowId:', rowId);
    
    try {

    // Get the edit modal
    const editModal = document.getElementById('editRowModal');
    if (!editModal) {
        console.error('Edit modal not found');
        return;
    }

    // Get the form in the modal
    const form = editModal.querySelector('form');
    if (!form) {
        console.error('Form not found in edit modal');
        return;
    }

    // Update the row ID in the form
    const rowIdInput = form.querySelector('input[name="row_id"]');
    if (rowIdInput) {
        rowIdInput.value = rowId;
    }

    // Use the passed data directly if available
    if (rowData && Object.keys(rowData).length > 0) {
        console.log('Using passed data directly:', rowData);
        
        // Prepare the data in the expected format
        const data = rowData;
        
        // Fill the form with the data
        fillEditForm(form, data);
        
        // Open the modal
        const modal = new bootstrap.Modal(editModal);
        modal.show();
        return;
    }
    
    // If no data is passed, try to fetch it via AJAX
    // Check if listId is available
    const listIdElement = document.getElementById('listId');
    if (!listIdElement || !listIdElement.value) {
        console.error('List ID not found');
        alert(_('Error: List ID not found'));
        return;
    }
    } catch (error) {
        console.error('Error in the first part of editRow:', error);
        alert(_('An error occurred while initializing the edit. See console for details.'));
        return;
    }
    
    const listId = listIdElement.value;
    console.log('Retrieved list ID:', listId);
    
    // Display a loading message
    console.log('Loading row data via AJAX...');
    
    try {
        // Make an AJAX request to get the complete row data
        fetch(`/api/lists/${listId}/data/${rowId}`)
            .then(response => {
                console.log('Response received:', response.status);
                if (!response.ok) {
                    throw new Error(`HTTP Error: ${response.status}`);
                }
                return response.json();
            })
        .then(responseData => {
            console.log('Data retrieved via API:', responseData);
            // Use API data to fill the form
            const data = responseData.data || {};
            fillEditForm(form, data);
            
            // Open the modal
            const modal = new bootstrap.Modal(editModal);
            modal.show();

        })
        .catch(error => {
            console.error('Error while fetching data:', error);
            alert(_('Error while fetching row data'));
        });
    } catch (error) {
        console.error('Error in the second part of editRow:', error);
        alert(_('An error occurred while fetching the data. See console for details.'));
    }
}

// Function to fill the edit form with data
function fillEditForm(form, data) {
    console.log('Filling form with data:', data);
    
    // For each form field
    form.querySelectorAll('input[name], select[name], textarea[name]').forEach(input => {
        const fieldName = input.name;
        if (fieldName === 'row_id') return; // Ignore the row_id field

        // Get the value from the data
        const value = data[fieldName] || '';
        console.log('Field:', fieldName, 'Value:', value);
        
        // If it's a date field
        if (input.closest('.flatpickr')) {
            console.log('Initializing Flatpickr for:', fieldName);
            // Destroy existing Flatpickr instance if it exists
            if (input._flatpickr) {
                input._flatpickr.destroy();
            }

            // Set the initial value
            input.value = value;

            // Create a new Flatpickr instance
            const fp = flatpickr(input.closest('.flatpickr'), {
                dateFormat: "d/m/Y",
                locale: "en", // Using English locale
                allowInput: true,
                altInput: true,
                altFormat: "d/m/Y",
                monthSelectorType: "static",
                disableMobile: true,
                wrap: true,
                clickOpens: false,
                onChange: function(selectedDates, dateStr, instance) {
                    console.log('Date selected:', dateStr);
                }
            });
        } 
        // If it's an IP field
        else if (input.classList.contains('ip-input')) {
            // Destroy existing IMask instance if it exists
            if (input.maskRef) {
                input.maskRef.destroy();
            }

            // Determine if it's an IPv4 or IPv6
            const isIPv6 = value.includes(':');
            
            // Update the IP type in the dropdown
            const dropdown = input.closest('.input-group').querySelector('.dropdown-toggle');
            if (dropdown) {
                dropdown.textContent = isIPv6 ? 'IPv6' : 'IPv4';
            }

            // Create the appropriate mask
            const maskOptions = isIPv6 ? {
                mask: `****:****:****:****:****:****:****:****`,
                definitions: {
                    '*': /[0-9a-fA-F]/
                },
                prepare: function (str) {
                    return str.toUpperCase();
                }
            } : {
                mask: function (value) {
                    if (value.includes('/')) {
                        return [
                            /\d/, /\d/, /\d/, '.',
                            /\d/, /\d/, /\d/, '.',
                            /\d/, /\d/, /\d/, '.',
                            /\d/, /\d/, /\d/, '/',
                            /\d/, /\d/
                        ];
                    }
                    return [
                        /\d/, /\d/, /\d/, '.',
                        /\d/, /\d/, /\d/, '.',
                        /\d/, /\d/, /\d/, '.',
                        /\d/, /\d/, /\d/
                    ];
                },
                lazy: false,
                autofix: true
            };

            // Initialize IMask
            const mask = IMask(input, maskOptions);
            input.maskRef = mask;

            // Set the value after initializing the mask
            if (value) {
                mask.value = value;
            }
        }
        // Otherwise, it's a normal field
        else {
            input.value = value;
        }
    });
}

// Function to submit the edit form
function submitEditRow(event) {
    event.preventDefault();
    console.log('Submitting edit form');

    // Get the form
    const form = event.target;
    const submitButton = form.querySelector('button[type="submit"]');

    // Prevent double submission
    if (form.dataset.submitting === 'true') {
        console.log('Form already submitting');
        return;
    }
    form.dataset.submitting = 'true';

    // Get the row ID
    const rowId = form.querySelector('input[name="row_id"]').value;

    // Get form data
    const formData = new FormData(form);
    const data = {};
    formData.forEach((value, key) => {
        if (key !== 'row_id') {
            data[key] = value;
        }
    });

    console.log('Data to send:', data);

    // Get the CSRF token
    const csrfMetaTag = document.querySelector('meta[name="csrf-token"]');
    if (!csrfMetaTag) {
        console.error('CSRF token not found');
        alert(_('Error: Missing CSRF token'));
        form.dataset.submitting = 'false';
        return;
    }
    
    const csrfToken = csrfMetaTag.getAttribute('content');

    // Disable the button
    submitButton.disabled = true;
    submitButton.textContent = _('Updating...');

    // Request configuration
    const requestOptions = {
        method: 'PUT',
        headers: {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'X-Requested-With': 'XMLHttpRequest',
            'X-CSRFToken': csrfToken
        },
        body: JSON.stringify(data),
        credentials: 'same-origin'
    };

    // Send the data
    fetch(`/api/lists/${listId}/data/${rowId}`, requestOptions)
    .then(response => {
        if (!response.ok) {
            return response.json().then(data => {
                throw new Error(data.error || _('Error during update'));
            });
        }
        return response.json();
    })
    .then(data => {
        if (!data.message) {
            throw new Error(_('Invalid server response'));
        }

        // Close the modal and remove the backdrop
        const modalElement = document.getElementById('editRowModal');
        const modal = bootstrap.Modal.getInstance(modalElement);
        if (modal) {
            modal.hide();
            // Ensure the backdrop is removed
            setTimeout(() => {
                // Manually remove the modal-backdrop class and overflow style
                const backdrop = document.querySelector('.modal-backdrop');
                if (backdrop) {
                    backdrop.remove();
                }
                // Restore normal page scrolling
                document.body.classList.remove('modal-open');
                document.body.style.overflow = '';
                document.body.style.paddingRight = '';
            }, 300);
        }

        // Update the row in the table
        return fetch(`/api/lists/${listId}/data/${rowId}`);
    })
    .then(response => {
        if (!response.ok) {
            throw new Error(_('Error fetching updated data'));
        }
        return response.json();
    })
    .then(rowData => {
        if (!rowData || !rowData.data) {
            throw new Error(_('Row data is invalid'));
        }

        // Find the row in the table
        const row = document.querySelector(`tr[data-row-id="${rowId}"]`);
        if (!row) {
            console.error('Row not found with tr[data-row-id]');
            
            // Try to find the row via the checkbox
            const checkbox = document.querySelector(`input.row-checkbox[data-row-id="${rowId}"]`);
            if (checkbox) {
                const checkboxRow = checkbox.closest('tr');
                if (checkboxRow) {
                    console.log('Row found via checkbox');
                    updateTableRow(checkboxRow, rowData.data);
                } else {
                    console.error('Could not find row even via checkbox');
                    throw new Error(_('Row not found'));
                }
            } else {
                console.error('Checkbox not found');
                throw new Error(_('Row not found'));
            }
        } else {
            console.log('Row found directly with tr[data-row-id]');
            updateTableRow(row, rowData.data);
        }
    })
    .catch(error => {
        console.error('Error:', error);
        alert(error.message || _('Error during update'));
    })
    .finally(() => {
        // Re-enable the button and form
        submitButton.disabled = false;
        submitButton.textContent = _('Update');
        form.dataset.submitting = 'false';
    });
}

// Function to update a row in the table
function updateTableRow(row, data) {
    console.log('Updating row with data:', data);
    
    try {
        // Use the DataTables API to update the row
        const dataTable = $('#dataTable').DataTable();
        const rowNode = $(row);
        
        if (!rowNode.length) {
            console.error('Row not found for update');
            return;
        }
        
        // Check if the first column is a checkbox
        const hasCheckbox = document.querySelector('#dataTable thead th input[type="checkbox"]') !== null;
        
        // Get the column order from the table headers
        const headers = Array.from(document.querySelectorAll('#dataTable thead th'));
        // Exclude the first (checkbox) and last (actions) columns if they exist
        const startIndex = hasCheckbox ? 1 : 0;
        const endIndex = document.querySelector('#dataTable thead th:last-child').textContent.trim() === 'Actions' ? -1 : undefined;
        const dataHeaders = headers.slice(startIndex, endIndex);
        
        console.log('Data headers:', dataHeaders.map(h => h.textContent.trim()));
        
        // Method 1: Direct DOM cell update
        dataHeaders.forEach((header, index) => {
            const columnName = header.textContent.trim();
            const cellIndex = startIndex + index; // Adjust index based on checkbox presence
            const cellNode = rowNode.find('td').eq(cellIndex);
            
            console.log(`Updating cell ${cellIndex} (${columnName}) with value:`, data[columnName]);
            
            if (cellNode.length) {
                // Update cell content
                cellNode.text(data[columnName] || '');
            } else {
                console.error(`Cell ${cellIndex} (${columnName}) not found`);
            }
        });
        
        // Method 2: Update via DataTables API
        // Prepare a data array for DataTables
        const rowDataArray = [];
        
        // Add the checkbox as the first cell if needed
        if (hasCheckbox) {
            rowDataArray.push(`<input type="checkbox" class="row-checkbox" data-row-id="${row.getAttribute('data-row-id')}">`); 
        }
        
        // Add data cells in column order
        dataHeaders.forEach(header => {
            const columnName = header.textContent.trim();
            rowDataArray.push(data[columnName] || '');
        });
        
        // Add action buttons as the last cell if the Actions column exists
        if (endIndex === -1) {
            const rowId = row.getAttribute('data-row-id');
            rowDataArray.push(`
                <button type="button" class="btn btn-sm btn-primary edit-row-btn" data-row-id="${rowId}" data-row-data='${JSON.stringify(data)}'>
                    <i class="fas fa-edit"></i>
                </button>
                <button type="button" class="btn btn-sm btn-danger" onclick="deleteRow('${rowId}')">
                    <i class="fas fa-trash"></i>
                </button>
            `);
        }
        
        // Update the row in DataTables
        const dtRow = dataTable.row(rowNode);
        dtRow.data(rowDataArray);
        dtRow.invalidate();
        dtRow.draw(false);
        
        // Update the data-row-data attributes of the edit buttons
        setTimeout(() => {
            const newEditButton = $(row).find('.edit-row-btn');
            if (newEditButton.length) {
                newEditButton.attr('data-row-data', JSON.stringify(data));
                console.log('data-row-data attribute updated with:', JSON.stringify(data));
                
                // Re-initialize event handlers for edit buttons
                initializeEditButtons();
            }
        }, 100);
        
        console.log('Row updated successfully via DataTables API');
        
        // Display a temporary success notification
        if (typeof showSuccess === 'function') {
            showSuccess(_('Row updated successfully'));
        } else {
            console.log('showSuccess function not available');
        }
    } catch (error) {
        console.error('Error while updating row:', error);
        if (typeof showError === 'function') {
            showError(_('Error while updating row. Please refresh the page.'));
        } else {
            console.log('showError function not available');
        }
    }
}

// Function to format dates
function formatDate(dateStr) {
    if (!dateStr) return '';
    
    try {
        // Convert string to Date object
        const date = new Date(dateStr);
        
        // Check if the date is valid
        if (isNaN(date.getTime())) {
            console.warn('Invalid date:', dateStr);
            return dateStr;
        }
        
        // Format the date to French format (DD/MM/YYYY)
        const day = String(date.getDate()).padStart(2, '0');
        const month = String(date.getMonth() + 1).padStart(2, '0'); // Months start at 0
        const year = date.getFullYear();
        
        return `${day}/${month}/${year}`;
    } catch (error) {
        console.error('Error while formatting date:', error);
        return dateStr;
    }
}

// Function to initialize Flatpickr on a date field
function initializeDatePicker(wrapper) {
    console.log('Initializing Flatpickr for wrapper:', wrapper);
    
    const input = wrapper.querySelector('[data-input]');
    if (!input) {
        console.error('Input not found in wrapper');
        return;
    }

    // Destroy existing instance if it exists
    if (input._flatpickr) {
        input._flatpickr.destroy();
    }
    
    // Create a new instance
    const fp = flatpickr(wrapper, {
        dateFormat: "d/m/Y",
        locale: "en",
        allowInput: true,
        altInput: true,
        altFormat: "d/m/Y",
        monthSelectorType: "static",
        disableMobile: true,
        wrap: true,
        clickOpens: false,
        onChange: function(selectedDates, dateStr, instance) {
            console.log('Date selected:', dateStr);
        }
    });

    // Set the value manually if needed
    const defaultDate = wrapper.querySelector('[data-default-date]');
    if (defaultDate) {
        const dateStr = defaultDate.getAttribute('data-default-date');
        if (dateStr) {
            input.value = dateStr;
        }
    }

    return fp;
}

// Function to initialize plugins on a modal
function initializeModalPlugins(modalElement) {
    if (!modalElement) return;

    // Initialize handlers for IP fields
    modalElement.querySelectorAll('.ip-input').forEach(input => {
        const dropdown = input.closest('.input-group').querySelector('.dropdown-toggle');
        const dropdownItems = input.closest('.input-group').querySelectorAll('.ip-type');

        dropdownItems.forEach(item => {
            item.addEventListener('click', (e) => {
                e.preventDefault();
                const type = e.target.dataset.type;
                dropdown.textContent = type === 'ipv4' ? 'IPv4' : 'IPv6';
                input.placeholder = type === 'ipv4' ? 
                    'e.g., 192.168.1.1 or 192.168.1.0/24' : 
                    'e.g., 2001:db8::1 or 2001:db8::/64';
            });
        });
    });
}

// Function to delete a row
function deleteRow(rowId) {
    if (!confirm(_('Are you sure you want to delete this row?'))) {
        return;
    }

    // Get the CSRF token
    const csrfMetaTag = document.querySelector('meta[name="csrf-token"]');
    if (!csrfMetaTag) {
        console.error('CSRF token not found');
        alert(_('Error: Missing CSRF token'));
        return;
    }
    
    const csrfToken = csrfMetaTag.getAttribute('content');

    // Request configuration
    const requestOptions = {
        method: 'DELETE',
        headers: {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'X-Requested-With': 'XMLHttpRequest',
            'X-CSRFToken': csrfToken
        },
        credentials: 'same-origin'
    };

    // Send the delete request
    fetch(`/api/lists/${listId}/data/${rowId}`, requestOptions)
    .then(response => {
        if (!response.ok) {
            return response.json().then(data => {
                throw new Error(data.error || _('Error during deletion'));
            });
        }
        return response.json();
    })
    .then(data => {
        if (data.message) {
            // Remove the row from the table using the DataTables API
            const dataTable = $('#dataTable').DataTable();
            
            // Find the row in DataTables
            const rowToRemove = $(`tr[data-row-id="${rowId}"]`);
            if (rowToRemove.length) {
                // Remove the row via DataTables API
                dataTable.row(rowToRemove).remove().draw();
                console.log('Row deleted successfully via DataTables API');
            } else {
                // If the row is not found with data-row-id, try with the checkbox
                const checkbox = $(`input.row-checkbox[data-row-id="${rowId}"]`);
                if (checkbox.length) {
                    const checkboxRow = checkbox.closest('tr');
                    if (checkboxRow.length) {
                        dataTable.row(checkboxRow).remove().draw();
                        console.log('Row deleted successfully via checkbox');
                    } else {
                        console.error('Could not find row even via checkbox');
                    }
                } else {
                    console.error('Checkbox not found');
                }
            }
        } else {
            throw new Error(data.error || _('Error during deletion'));
        }
    })
    .catch(error => {
        console.error('Error:', error);
        alert(error.message || _('Error during deletion'));
    });
}

// Function to initialize IMask for IPs
function initializeIPMask(input) {
    let currentMask = null;

    function updateMask(type) {
        if (currentMask) {
            currentMask.destroy();
        }

        currentMask = type === 'ipv6' ? createIPv6Mask(input) : createIPv4Mask(input);
    }

    // Initialize with IPv4 by default
    updateMask('ipv4');

    // Handle IP type change
    const dropdownItems = input.closest('.input-group').querySelectorAll('.ip-type');
    dropdownItems.forEach(item => {
        item.addEventListener('click', (e) => {
            e.preventDefault();
            const type = e.target.dataset.type;
            const button = input.closest('.input-group').querySelector('.dropdown-toggle');
            button.textContent = type === 'ipv4' ? 'IPv4' : 'IPv6';
            updateMask(type);
            input.value = '';
            input.placeholder = type === 'ipv6' ? 
                'e.g., 2001:db8::1 or 2001:db8::/64' : 
                'e.g., 192.168.1.1 or 192.168.1.0/24';
        });
    });
}

function createIPv4Mask(input) {
    return IMask(input, {
        mask: function (value) {
            // Function to create a pattern for an octet (0-255)
            const octetPattern = /^[0-9]{1,3}$/;
            
            // Split the IP into octets
            const parts = value.split('.');
            const hasCIDR = value.includes('/');
            
            // Validate each octet
            parts.forEach((part, index) => {
                if (index < 4 && part) {  // The first 4 octets
                    const num = parseInt(part);
                    if (!octetPattern.test(part) || num < 0 || num > 255) {
                        return false;
                    }
                }
            });
            
            // If we have a CIDR, validate the mask
            if (hasCIDR && parts[4]) {
                const mask = parseInt(parts[4]);
                if (isNaN(mask) || mask < 0 || mask > 32) {
                    return false;
                }
            }
            
            return true;
        },
        prepare: function (value) {
            return value.replace(/[^0-9./]/g, '');
        },
        commit: function (value) {
            // Format the IP correctly
            const parts = value.split('.');
            const formattedParts = parts.map((part, index) => {
                if (index < 4) {  // The first 4 octets
                    const num = parseInt(part);
                    return isNaN(num) ? '' : num.toString();
                }
                return part;  // For the CIDR
            });
            return formattedParts.join('.');
        }
    });
}

function createIPv6Mask(input) {
    return IMask(input, {
        mask: function (value) {
            const parts = value.split(':');
            const hasCIDR = value.includes('/');
            
            // Validate each hexadecimal segment
            for (let i = 0; i < parts.length; i++) {
                const part = parts[i];
                if (i < 8) {  // The 8 segments of IPv6
                    if (part && !/^[0-9A-Fa-f]{1,4}$/.test(part)) {
                        return false;
                    }
                } else if (hasCIDR) {  // The CIDR mask
                    const mask = parseInt(part);
                    if (isNaN(mask) || mask < 0 || mask > 128) {
                        return false;
                    }
                }
            }
            
            return true;
        },
        prepare: function (value) {
            return value.replace(/[^0-9A-Fa-f:/]/g, '');
        }
    });
}

// Function to initialize DataTables
function initializeDataTables() {
    const dataTable = $('#dataTable');
    if (dataTable.length) {
        // Determine the language BEFORE initialization
        const langMap = { fr: 'fr-FR', en: 'en-US' };
        const langCode = window.currentLanguage && langMap[window.currentLanguage] ? langMap[window.currentLanguage] : 'en-US';
        dataTable.DataTable({
            dom: '<"row"<"col-sm-6"l><"col-sm-6"f>>rt<"row justify-content-center"<"col-auto"p>>i',
            language: {
                url: `/static/js/datatables/i18n/${langCode}.json`
            },
            drawCallback: function() {
                console.log('DataTable redrawn');
                initializeEditButtons();
            },
            initComplete: function() {
                console.log('DataTable initialized');
                if (!multipleSelectionInitialized) {
                    setupMultipleSelection();
                }
            }
        });
    }
}

// Initialization when the DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    console.log('JavaScript loaded and initialized');
    
    // Initialize DataTables
    initializeDataTables();
    
    // Initialize plugins on modals
    const addRowModal = document.getElementById('addRowModal');
    if (addRowModal) {
        addRowModal.addEventListener('shown.bs.modal', function () {
            initializeModalPlugins(addRowModal);
        });
    }

    const editRowModal = document.getElementById('editRowModal');
    if (editRowModal) {
        editRowModal.addEventListener('shown.bs.modal', function () {
            initializeModalPlugins(editRowModal);
        });
    }

    // Initialize IMask for IPs
    const ipInputs = document.querySelectorAll('.ip-input');
    ipInputs.forEach(input => {
        initializeIPMask(input);
    });

    // Add event handlers for forms
    const importForm = document.getElementById('importForm');
    if (importForm) {
        importForm.addEventListener('submit', submitImport);
    }

    const addRowForm = document.getElementById('addRowForm');
    if (addRowForm) {
        addRowForm.addEventListener('submit', submitAddRow);
    }

    const editRowForm = document.getElementById('editRowForm');
    if (editRowForm) {
        editRowForm.addEventListener('submit', submitEditRow);
    }
});

// Function to reset checkboxes
function resetCheckboxes() {
    const selectAllCheckbox = document.getElementById('selectAll');
    const deleteSelectedBtn = document.getElementById('deleteSelectedBtn');
    
    if (selectAllCheckbox) {
        selectAllCheckbox.checked = false;
    }
    
    if (deleteSelectedBtn) {
        deleteSelectedBtn.style.display = 'none';
    }
}

// Function to update the delete button's visibility
function updateDeleteButtonVisibility() {
    const deleteSelectedBtn = document.getElementById('deleteSelectedBtn');
    if (!deleteSelectedBtn) return;
    
    const selectedCount = document.querySelectorAll('#dataTable tbody .row-checkbox:checked').length;
    console.log('Number of selected checkboxes:', selectedCount);
    
    if (selectedCount > 0) {
        deleteSelectedBtn.style.display = 'inline-block';
        deleteSelectedBtn.textContent = interpolate(_('Delete (%s)'), [selectedCount]);
    } else {
        deleteSelectedBtn.style.display = 'none';
    }
}
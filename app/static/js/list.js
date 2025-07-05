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
        alert(t('list.no_rows_selected_alert'));
        return;
    }
    
    // Mark that deletion is in progress
    deleteInProgress = true;
    
    // Ask for confirmation once for all rows
    if (!confirm(t('list.delete_rows_confirm', { count: selectedCount }))) {
        // Reset the state if the user cancels
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
            if (row?.getAttribute('data-row-id')) {
                rowIds.push(parseInt(row.getAttribute('data-row-id')));
            }
        }
    });
    
    console.log('IDs of rows to delete:', rowIds);
    
    if (rowIds.length === 0) {
        alert(t('list.no_valid_row_ids_alert'));
        return;
    }
    
    // Get the CSRF token
    const csrfMetaTag = document.querySelector('meta[name="csrf-token"]');
    if (!csrfMetaTag) {
        console.error('CSRF token not found');
        alert(t('list.csrf_token_missing_alert'));
        return;
    }
    
    const csrfToken = csrfMetaTag.getAttribute('content');
    
    // Get the list ID from the hidden element (preferred method)
    const listIdInput = document.getElementById('listId');
    if (listIdInput?.value) {
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
    
    // If we get here, it means we could not get the list ID
    console.error('List ID not found');
    alert(t('list.list_id_missing_alert'));
}

// Function to perform the delete request
function performDeleteRequest(listId, rowIds, csrfToken, dataTable, selectedCheckboxes, selectedCount) {
    console.log('%c=== Start of performDeleteRequest function ===', 'background: #222; color: #bada55');
    console.log('Sending delete request for list:', listId, 'with rows:', rowIds);
    
    // Disable the delete button during processing
    const deleteSelectedBtn = document.getElementById('deleteSelectedBtn');
    if (deleteSelectedBtn) {
        deleteSelectedBtn.disabled = true;
        deleteSelectedBtn.innerHTML = `<i class="fas fa-spinner fa-spin"></i> ${t('list.deleting')}`;
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
            // If we can't parse JSON, throw an error with the HTTP status
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
            deleteSelectedBtn.innerHTML = `<i class="fas fa-trash"></i> ${t('list.delete_selection')}`;
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
            
            // Reset the checkboxes
            resetCheckboxes();
            
            // Display a success message
            showFlashMessage(t('list.delete_selected_success', { count: data.deleted_count }), 'success');
        } else {
            // The request failed or no rows were deleted
            console.error('Deletion error:', data.error);
            alert(t('list.delete_selected_error') + (data.error || t('list.no_rows_deleted')));
        }
    })
    .catch(error => {
        console.error('Error during deletion:', error);
        
        // Re-enable the delete button
        if (deleteSelectedBtn) {
            deleteSelectedBtn.disabled = false;
            deleteSelectedBtn.innerHTML = `<i class="fas fa-trash"></i> ${t('list.delete_selection')}`;
        }
        
        alert(t('list.delete_selected_error') + error.message);
    })
    .finally(() => {
        // Reset the deletion state
        deleteInProgress = false;
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
        console.log('Form already being submitted');
        return;
    }
    form.dataset.submitting = 'true';

    // Get the row ID
    const rowId = form.querySelector('input[name="row_id"]').value;

    // Get the form data
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
        alert(t('list.csrf_token_missing_alert'));
        form.dataset.submitting = 'false';
        return;
    }
    
    const csrfToken = csrfMetaTag.getAttribute('content');

    // Disable the button
    submitButton.disabled = true;
    submitButton.textContent = t('list.updating');

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
                throw new Error(data.error || t('list.update_error'));
            });
        }
        return response.json();
    })
    .then(data => {
        if (!data.message) {
            throw new Error(t('list.invalid_server_response'));
        }

        // Close the modal and remove the backdrop
        const modalElement = document.getElementById('editRowModal');
        const modal = bootstrap.Modal.getInstance(modalElement);
        if (modal) {
            modal.hide();
            // Ensure the backdrop is removed
            setTimeout(() => {
                // Manually remove the modal-backdrop class and the overflow style
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
            throw new Error(t('list.retrieve_data_error'));
        }
        return response.json();
    })
    .then(rowData => {
        if (!rowData || !rowData.data) {
            throw new Error(t('list.invalid_row_data'));
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
                    console.error('Could not find the row even via the checkbox');
                    throw new Error(t('list.row_not_found'));
                }
            } else {
                console.error('Checkbox not found');
                throw new Error(t('list.row_not_found'));
            }
        } else {
            console.log('Row found directly with tr[data-row-id]');
            updateTableRow(row, rowData.data);
        }
    })
    .catch(error => {
        console.error('Error:', error);
        alert(t('list.update_error_alert') + error.message);
    })
    .finally(() => {
        // Re-enable the button and the form
        submitButton.disabled = false;
        submitButton.textContent = t('list.update');
        form.dataset.submitting = 'false';
    });
}

// Function to delete a row
function deleteRow(rowId) {
    if (!confirm(t('list.delete_row_confirm'))) {
        return;
    }

    // Get the CSRF token
    const csrfMetaTag = document.querySelector('meta[name="csrf-token"]');
    if (!csrfMetaTag) {
        console.error('CSRF token not found');
        alert(t('list.csrf_token_missing_alert'));
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
                throw new Error(data.error || t('list.delete_error'));
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
                showFlashMessage(t('list.delete_row_success'), 'success');
            } else {
                // If the row is not found with data-row-id, try with the checkbox
                const checkbox = $(`input.row-checkbox[data-row-id="${rowId}"]`);
                if (checkbox.length) {
                    const checkboxRow = checkbox.closest('tr');
                    if (checkboxRow.length) {
                        dataTable.row(checkboxRow).remove().draw();
                        console.log('Row deleted successfully via checkbox');
                        showFlashMessage(t('list.delete_row_success'), 'success');
                    } else {
                        console.error('Could not find the row even via the checkbox');
                    }
                } else {
                    console.error('Checkbox not found');
                }
            }
        } else {
            throw new Error(data.error || t('list.delete_error'));
        }
    })
    .catch(error => {
        console.error('Error:', error);
        alert(t('list.delete_error_alert') + error.message);
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
                'e.g.: 2001:db8::1 or 2001:db8::/64' : 
                'e.g.: 192.168.1.1 or 192.168.1.0/24';
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
            
            // If there is a CIDR, validate the mask
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
            return value.replace(/[\da-fA-F]/g, '');
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

// Function to update the visibility of the delete button
function updateDeleteButtonVisibility() {
    const deleteSelectedBtn = document.getElementById('deleteSelectedBtn');
    if (!deleteSelectedBtn) return;
    
    const selectedCount = document.querySelectorAll('#dataTable tbody .row-checkbox:checked').length;
    console.log('Number of selected checkboxes:', selectedCount);
    
    if (selectedCount > 0) {
        deleteSelectedBtn.style.display = 'inline-block';
        deleteSelectedBtn.textContent = t('list.delete_button_count', { count: selectedCount });
    } else {
        deleteSelectedBtn.style.display = 'none';
    }
}
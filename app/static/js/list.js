// Variable pour éviter les appels multiples à deleteSelectedRows
let deleteInProgress = false;

// Fonction pour supprimer les lignes sélectionnées
function deleteSelectedRows() {
    console.log('%c=== Début de la fonction deleteSelectedRows ===', 'background: #222; color: #bada55');
    
    // Vérifier si une suppression est déjà en cours
    if (deleteInProgress) {
        console.log('Une suppression est déjà en cours, annulation de cet appel');
        return;
    }
    
    // Obtenir toutes les cases à cocher sélectionnées avec le sélecteur exact
    const selectedCheckboxes = document.querySelectorAll('#dataTable tbody .row-checkbox:checked');
    console.log('Nombre de cases à cocher sélectionnées:', selectedCheckboxes.length);
    const selectedCount = selectedCheckboxes.length;
    
    if (selectedCount === 0) {
        alert('Aucune ligne sélectionnée');
        return;
    }
    
    // Marquer que la suppression est en cours
    deleteInProgress = true;
    
    // Demander confirmation une seule fois pour toutes les lignes
    if (!confirm(`Êtes-vous sûr de vouloir supprimer ${selectedCount} ligne(s) ?`)) {
        // Réinitialiser l'état si l'utilisateur annule
        deleteInProgress = false;
        return;
    }
    
    // Récupérer l'instance DataTables
    const dataTable = $('#dataTable').DataTable();
    
    // Récupérer les IDs des lignes à supprimer
    const rowIds = [];
    selectedCheckboxes.forEach(checkbox => {
        // Récupérer l'ID de la ligne à partir de l'attribut data-row-id
        const rowId = checkbox.getAttribute('data-row-id');
        if (rowId) {
            rowIds.push(parseInt(rowId));
        } else {
            // Si data-row-id n'est pas disponible sur la case à cocher, essayer de le récupérer depuis la ligne
            const row = checkbox.closest('tr');
            if (row && row.getAttribute('data-row-id')) {
                rowIds.push(parseInt(row.getAttribute('data-row-id')));
            }
        }
    });
    
    console.log('IDs des lignes à supprimer:', rowIds);
    
    if (rowIds.length === 0) {
        alert('Aucun ID de ligne valide trouvé');
        return;
    }
    
    // Récupérer le token CSRF
    const csrfMetaTag = document.querySelector('meta[name="csrf-token"]');
    if (!csrfMetaTag) {
        console.error('Token CSRF non trouvé');
        alert('Erreur : Token CSRF manquant');
        return;
    }
    
    const csrfToken = csrfMetaTag.getAttribute('content');
    
    // Récupérer l'ID de la liste depuis l'élément caché (méthode préférée)
    const listIdInput = document.getElementById('listId');
    if (listIdInput && listIdInput.value) {
        const listId = parseInt(listIdInput.value);
        if (!isNaN(listId)) {
            console.log('ID de liste récupéré depuis l\'élément caché:', listId);
            // Envoyer la requête avec l'ID récupéré
            performDeleteRequest(listId, rowIds, csrfToken, dataTable, selectedCheckboxes, selectedCount);
            return;
        }
    }
    
    // Si l'ID n'est pas disponible dans l'élément caché, essayer de le récupérer depuis l'URL
    const pathParts = window.location.pathname.split('/');
    const listsIndex = pathParts.indexOf('lists');
    
    if (listsIndex !== -1 && listsIndex + 1 < pathParts.length) {
        const potentialId = pathParts[listsIndex + 1];
        if (potentialId && !isNaN(parseInt(potentialId))) {
            const listId = parseInt(potentialId);
            console.log('ID de liste extrait de l\'URL:', listId);
            performDeleteRequest(listId, rowIds, csrfToken, dataTable, selectedCheckboxes, selectedCount);
            return;
        }
    }
    
    // Si on arrive ici, c'est qu'on n'a pas pu récupérer l'ID de liste
    console.error('ID de liste non trouvé');
    alert('Erreur : ID de liste manquant');
}

// Fonction pour effectuer la requête de suppression
function performDeleteRequest(listId, rowIds, csrfToken, dataTable, selectedCheckboxes, selectedCount) {
    console.log('%c=== Début de la fonction performDeleteRequest ===', 'background: #222; color: #bada55');
    console.log('Envoi de la requête de suppression pour la liste:', listId, 'avec les lignes:', rowIds);
    
    // Désactiver le bouton de suppression pendant le traitement
    const deleteSelectedBtn = document.getElementById('deleteSelectedBtn');
    if (deleteSelectedBtn) {
        deleteSelectedBtn.disabled = true;
        deleteSelectedBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Suppression en cours...';
    }
    
    // Construire l'URL avec le format exact attendu par le backend
    const deleteUrl = `/api/lists/${listId}/data/bulk-delete`;
    
    // Envoyer la requête de suppression
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
        console.log('Statut de la réponse:', response.status);
        // Même si la réponse n'est pas OK (404, etc.), on veut quand même parser le JSON
        // pour obtenir le message d'erreur
        return response.json().catch(e => {
            // Si on ne peut pas parser le JSON, on lance une erreur avec le statut HTTP
            throw new Error(`Erreur HTTP ${response.status}`);
        }).then(data => {
            // Si la réponse n'est pas OK, on ajoute le statut HTTP aux données
            if (!response.ok) {
                data.httpStatus = response.status;
            }
            return data;
        });
    })
    .then(data => {
        console.log('Données de la réponse:', data);
        
        // Réactiver le bouton de suppression
        if (deleteSelectedBtn) {
            deleteSelectedBtn.disabled = false;
            deleteSelectedBtn.innerHTML = `<i class="fas fa-trash"></i> Supprimer la sélection`;
            deleteSelectedBtn.style.display = 'none'; // Cacher le bouton après la suppression
        }
        
        // Vérifier explicitement le champ success
        if (data.success === true) {
            console.log('Suppression réussie!');
            
            // Supprimer les lignes du tableau
            selectedCheckboxes.forEach(checkbox => {
                const row = checkbox.closest('tr');
                if (row) {
                    dataTable.row(row).remove();
                }
            });
            
            // Redessiner le tableau
            dataTable.draw();
            
            // Réinitialiser les cases à cocher
            resetCheckboxes();
            
            // Afficher un message de succès
            alert(data.message || `${data.deleted_count} ligne(s) supprimée(s) avec succès`);
        } else {
            // La requête a échoué ou aucune ligne n'a été supprimée
            console.error('Erreur de suppression:', data.error);
            alert('Erreur lors de la suppression: ' + (data.error || 'Aucune ligne n\'a pu être supprimée'));
        }
    })
    .catch(error => {
        console.error('Erreur lors de la suppression:', error);
        
        // Réactiver le bouton de suppression
        if (deleteSelectedBtn) {
            deleteSelectedBtn.disabled = false;
            deleteSelectedBtn.innerHTML = `<i class="fas fa-trash"></i> Supprimer la sélection`;
        }
        
        alert('Erreur lors de la suppression: ' + error.message);
    })
    .finally(() => {
        // Réinitialiser l'état de suppression
        deleteInProgress = false;
    });
}

// Variable pour suivre si la sélection multiple a déjà été configurée
let multipleSelectionInitialized = false;

// Fonction pour gérer la sélection multiple des lignes
function setupMultipleSelection() {
    // Vérifier si la sélection multiple a déjà été configurée
    if (multipleSelectionInitialized) {
        console.log('La sélection multiple a déjà été configurée, ignorant cette initialisation');
        return;
    }
    
    console.log('Configuration de la sélection multiple');
    
    const selectAllCheckbox = document.getElementById('selectAll');
    const deleteSelectedBtn = document.getElementById('deleteSelectedBtn');
    const dataTable = document.getElementById('dataTable');
    let dataTableApi = null;
    
    // Initialiser l'API DataTables si elle existe
    if (dataTable && $.fn.DataTable.isDataTable('#dataTable')) {
        dataTableApi = $(dataTable).DataTable();
    }

    // Fonction pour mettre à jour l'affichage du bouton de suppression
    function updateDeleteButtonVisibility() {
        const selectedCount = document.querySelectorAll('#dataTable tbody .row-checkbox:checked').length;
        if (selectedCount > 0) {
            deleteSelectedBtn.style.display = 'inline-block';
            deleteSelectedBtn.textContent = `Supprimer (${selectedCount})`;
        } else {
            deleteSelectedBtn.style.display = 'none';
        }
    }

    // Gestionnaire pour la case "Tout sélectionner"
    if (selectAllCheckbox) {
        // Utiliser jQuery pour gérer l'événement change
        $(selectAllCheckbox).off('change').on('change', function() {
            const isChecked = this.checked;
            
            // Utiliser DataTables API pour sélectionner toutes les cases à cocher visibles
            const table = $('#dataTable').DataTable();
            
            // Sélectionner uniquement les cases à cocher des lignes actuellement visibles dans le DOM
            $('#dataTable tbody tr:visible .row-checkbox').prop('checked', isChecked);
            
            // Mettre à jour l'affichage du bouton de suppression
            updateDeleteButtonVisibility();
        });
    }

    // Utiliser la délégation d'événements avec jQuery pour les cases à cocher des lignes
    $(document).off('change', '.row-checkbox').on('change', '.row-checkbox', function() {
        // Mettre à jour l'affichage du bouton de suppression
        updateDeleteButtonVisibility();
        
        // Mettre à jour la case "Tout sélectionner"
        if (selectAllCheckbox) {
            const totalCheckboxes = $('.row-checkbox').length;
            const checkedCheckboxes = $('.row-checkbox:checked').length;
            
            // Mettre à jour l'état de la case "Tout sélectionner"
            selectAllCheckbox.checked = (totalCheckboxes > 0 && totalCheckboxes === checkedCheckboxes);
        }
    });

    // Gestionnaire pour le bouton de suppression multiple
    if (deleteSelectedBtn) {
        // Supprimer tous les gestionnaires d'événements existants
        $(deleteSelectedBtn).off('click');
        
        // Ajouter un seul gestionnaire d'événement
        $(deleteSelectedBtn).on('click', function(e) {
            // Empêcher le comportement par défaut et la propagation
            e.preventDefault();
            e.stopPropagation();
            
            console.log('%c=== Clic sur le bouton de suppression multiple ===', 'background: #222; color: #bada55');
            // Appeler la fonction de suppression multiple
            deleteSelectedRows();
        });
    }
    
    // Marquer la sélection multiple comme configurée
    multipleSelectionInitialized = true;
}

// Variable pour éviter les soumissions multiples du formulaire d'importation
let importInProgress = false;

// Fonction pour importer des données
function submitImport(event) {
    event.preventDefault();
    console.log('Fonction submitImport appelée');
    
    // Vérifier si un import est déjà en cours
    if (importInProgress) {
        console.log('Un import est déjà en cours, annulation de cet appel');
        return;
    }
    
    // Marquer que l'import est en cours
    importInProgress = true;
    
    const form = event.target;
    const submitButton = form.querySelector('button[type="submit"]');
    const formData = new FormData(form);

    submitButton.disabled = true;
    submitButton.textContent = 'Import en cours...';

    console.log('Envoi de la requête d\'import...');
    console.log('FormData:', Array.from(formData.entries()));

    // Récupérer le token CSRF
    const csrfMetaTag = document.querySelector('meta[name="csrf-token"]');
    if (!csrfMetaTag) {
        console.error('Token CSRF non trouvé');
        alert('Erreur : Token CSRF manquant');
        submitButton.disabled = false;
        submitButton.textContent = 'Importer';
        return;
    }
    
    const csrfToken = csrfMetaTag.getAttribute('content');

    // Configuration de la requête
    const requestOptions = {
        method: 'POST',
        headers: {
            'X-CSRFToken': csrfToken
        },
        body: formData,
        credentials: 'same-origin'
    };
    
    console.log('Options de la requête:', requestOptions);

    fetch(`/api/lists/${listId}/import`, requestOptions)
    .then(response => {
        console.log('Réponse reçue:', response);
        return response.json().then(data => {
            if (!response.ok) {
                throw new Error(data.error || 'Erreur lors de l\'import');
            }
            return data;
        });
    })
    .then(data => {
        console.log('Données reçues:', data);
        if (data.message) {
            // Fermer le modal
            const modal = bootstrap.Modal.getInstance(document.getElementById('importModal'));
            modal.hide();
            // Recharger la page
            window.location.reload();
        } else {
            throw new Error(data.error || 'Erreur lors de l\'import');
        }
    })
    .catch(error => {
        console.error('Error:', error);
        alert(error.message || 'Erreur lors de l\'import');
    })
    .finally(() => {
        // Réactiver le bouton
        submitButton.disabled = false;
        submitButton.textContent = 'Importer';
        // Réinitialiser l'état d'importation
        importInProgress = false;
        console.log('Import terminé, réinitialisation de l\'importInProgress');
    });
}

// Fonction pour ajouter une ligne
function submitAddRow(event) {
    event.preventDefault();
    
    // Éviter la double soumission
    const form = event.target;
    if (form.dataset.submitting === 'true') {
        console.log('Formulaire déjà en cours de soumission');
        return;
    }
    form.dataset.submitting = 'true';
    
    console.log('Soumission du formulaire d\'ajout');

    // Récupérer le formulaire et le bouton
    const submitButton = form.querySelector('button[type="submit"]');

    // Récupérer les données du formulaire
    const formData = new FormData(form);
    const data = {};
    
    // Récupérer tous les champs du formulaire et leurs types
    const inputs = form.querySelectorAll('input, select, textarea');
    
    // Parcourir tous les champs pour collecter les données avec le bon type
    inputs.forEach(input => {
        if (!input.name || input.name === '') return;
        
        let value = input.value.trim();
        
        // Ignorer les champs vides
        if (value === '') {
            data[input.name] = '';
            return;
        }
        
        // Traitement spécial selon le type de champ
        if (input.classList.contains('datepicker')) {
            // Pour les dates, s'assurer qu'elles sont au format DD/MM/YYYY
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
            // Pour les nombres, convertir en nombre
            value = value !== '' ? Number(value) : '';
        }
        
        data[input.name] = value;
    });

    console.log('Données à envoyer:', data);

    // Récupérer le token CSRF
    const csrfMetaTag = document.querySelector('meta[name="csrf-token"]');
    if (!csrfMetaTag) {
        console.error('Token CSRF non trouvé');
        alert('Erreur : Token CSRF manquant');
        form.dataset.submitting = 'false';
        return;
    }
    
    const csrfToken = csrfMetaTag.getAttribute('content');

    // Récupérer l'ID de la liste
    const listIdElement = document.getElementById('listId');
    const currentListId = listIdElement ? listIdElement.value : listId;
    
    if (!currentListId) {
        console.error('ID de liste non trouvé');
        alert('Erreur : ID de liste manquant');
        form.dataset.submitting = 'false';
        return;
    }
    
    console.log('ID de liste utilisé pour l\'ajout:', currentListId);

    // Désactiver le bouton
    submitButton.disabled = true;
    submitButton.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Ajout...';

    let newRowId = null;

    // Configuration de la requête
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

    // URL exacte pour l'API
    const apiUrl = `/api/lists/${currentListId}/data`;
    console.log('URL de l\'API:', apiUrl);

    // Envoyer les données
    fetch(apiUrl, requestOptions)
    .then(response => {
        console.log('Statut de la réponse:', response.status);
        // Même si la réponse n'est pas OK, on veut quand même parser le JSON
        return response.json().catch(e => {
            // Si on ne peut pas parser le JSON, on lance une erreur avec le statut HTTP
            throw new Error(`Erreur HTTP ${response.status}`);
        }).then(data => {
            // Si la réponse n'est pas OK, on ajoute le statut HTTP aux données et on lance une erreur
            if (!response.ok) {
                const errorMsg = data.error || `Erreur lors de l'ajout (${response.status})`;
                throw new Error(errorMsg);
            }
            return data;
        });
    })
    .then(data => {
        console.log('Données reçues après ajout:', data);
        if (!data.message || !data.row_id) {
            throw new Error('Réponse invalide du serveur');
        }
        
        newRowId = data.row_id;
        
        // Fermer le modal
        const modal = bootstrap.Modal.getInstance(document.getElementById('addRowModal'));
        if (modal) {
            modal.hide();
        }

        // Réinitialiser le formulaire
        form.reset();

        // Attendre un peu avant de récupérer les données pour s'assurer qu'elles sont bien enregistrées
        return new Promise(resolve => setTimeout(resolve, 300))
            .then(() => fetch(`/api/lists/${currentListId}/data/${newRowId}`));
    })
    .then(response => {
        if (!response.ok) {
            throw new Error('Erreur lors de la récupération des données de la ligne');
        }
        return response.json();
    })
    .then(rowData => {
        console.log('Données de la ligne reçues:', rowData);
        
        if (!rowData || !rowData.data) {
            throw new Error('Les données de la ligne sont invalides');
        }

        // Ajouter la nouvelle ligne au tableau en utilisant l'API DataTables
        const dataTable = $('#dataTable').DataTable();
        
        // Préparer les données pour DataTables
        const rowDataArray = [];
        
        // Vérifier si la première colonne est une case à cocher
        const hasCheckbox = document.querySelector('#dataTable thead th input[type="checkbox"]') !== null;
        
        // Ajouter la case à cocher comme première cellule si nécessaire
        if (hasCheckbox) {
            rowDataArray.push(`<input type="checkbox" class="row-checkbox" data-row-id="${rowData.row_id}">`);
        }
        
        // Récupérer l'ordre des colonnes depuis les en-têtes du tableau
        const headers = Array.from(document.querySelectorAll('#dataTable thead th'));
        // Exclure la première colonne (checkbox) et la dernière colonne (actions) si elles existent
        const startIndex = hasCheckbox ? 1 : 0;
        const endIndex = document.querySelector('#dataTable thead th:last-child').textContent.trim() === 'Actions' ? -1 : undefined;
        const dataHeaders = headers.slice(startIndex, endIndex);
        
        // Ajouter les cellules de données dans l'ordre des colonnes
        dataHeaders.forEach(header => {
            const columnName = header.textContent.trim();
            rowDataArray.push(rowData.data[columnName] || '');
        });
        
        // Ajouter les boutons d'action comme dernière cellule si la colonne Actions existe
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
        
        // Ajouter la ligne à DataTables
        const newRowNode = dataTable.row.add(rowDataArray).draw().node();
        
        // Ajouter l'attribut data-row-id à la ligne
        $(newRowNode).attr('data-row-id', rowData.row_id);
        
        // Réinitialiser les gestionnaires d'événements pour les boutons d'édition
        initializeEditButtons();
        
        console.log('Ligne ajoutée avec succès via DataTables API');
        
        // Afficher une notification temporaire de succès
        if (typeof showSuccess === 'function') {
            showSuccess('Ligne ajoutée avec succès');
        } else {
            console.log('Fonction showSuccess non disponible');
        }
    })
    .catch(error => {
        console.error('Error:', error);
        alert(error.message || 'Erreur lors de l\'ajout');
    })
    .finally(() => {
        // Réactiver le bouton et le formulaire
        submitButton.disabled = false;
        submitButton.innerHTML = 'Ajouter';
        form.dataset.submitting = 'false';
    });
}

// Variable pour suivre si les gestionnaires d'événements ont déjà été initialisés
let editButtonsInitialized = false;

// Fonction d'initialisation des boutons d'édition - extraite pour éviter les initialisations multiples
function initializeEditButtons() {
    // Vérifier si les boutons ont déjà été initialisés
    if (editButtonsInitialized) {
        console.log('Les boutons d\'\u00e9dition ont déjà été initialisés, ignorant cette initialisation');
        return;
    }
    
    console.log('Initialisation des boutons d\'\u00e9dition');
    
    // Ajouter des gestionnaires d'événements pour les boutons d'édition
    document.querySelectorAll('.edit-row-btn').forEach(button => {
        console.log('Ajout d\'un gestionnaire pour le bouton d\'\u00e9dition:', button);
        button.addEventListener('click', function() {
            const rowId = this.getAttribute('data-row-id');
            const rowDataStr = this.getAttribute('data-row-data');
            console.log('Clic sur le bouton d\'\u00e9dition pour la ligne:', rowId);
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
        });
    });
    
    // Ajouter un gestionnaire d'événement pour le bouton d'annulation du modal d'édition
    const cancelEditButton = document.querySelector('#editRowModal .btn-secondary[data-bs-dismiss="modal"]');
    if (cancelEditButton) {
        console.log('Ajout d\'un gestionnaire pour le bouton d\'annulation du modal d\'édition');
        cancelEditButton.addEventListener('click', function() {
            // S'assurer que le backdrop est supprimé
            setTimeout(() => {
                // Supprimer manuellement la classe modal-backdrop et le style overflow
                const backdrop = document.querySelector('.modal-backdrop');
                if (backdrop) {
                    backdrop.remove();
                }
                // Rétablir le défilement normal de la page
                document.body.classList.remove('modal-open');
                document.body.style.overflow = '';
                document.body.style.paddingRight = '';
            }, 300);
        });
    }
    
    // Marquer les boutons comme initialisés
    editButtonsInitialized = true;
}

// Ajouter un écouteur d'événement pour initialiser les gestionnaires au chargement de la page
document.addEventListener('DOMContentLoaded', function() {
    console.log('Page chargée, initialisation des gestionnaires d\'\u00e9vénements');
    
    // Initialiser les boutons d'édition
    initializeEditButtons();
});

// Fonction pour éditer une ligne
function editRow(rowId, rowData) {
    console.log('%c=== Début de la fonction editRow ===', 'background: #222; color: #bada55');
    console.log('Edition de la ligne:', rowId);
    console.log('Type de rowData:', typeof rowData);
    console.log('Données de la ligne:', rowData);
    
    // Fonction appelée avec rowId
    console.log('Fonction editRow appelée avec rowId:', rowId);
    
    try {

    // Récupérer le modal d'édition
    const editModal = document.getElementById('editRowModal');
    if (!editModal) {
        console.error('Modal d\'édition non trouvé');
        return;
    }

    // Récupérer le formulaire dans le modal
    const form = editModal.querySelector('form');
    if (!form) {
        console.error('Formulaire non trouvé dans le modal d\'édition');
        return;
    }

    // Mettre à jour l'ID de la ligne dans le formulaire
    const rowIdInput = form.querySelector('input[name="row_id"]');
    if (rowIdInput) {
        rowIdInput.value = rowId;
    }

    // Utiliser directement les données passées si elles sont disponibles
    if (rowData && Object.keys(rowData).length > 0) {
        console.log('Utilisation des données passées directement:', rowData);
        
        // Préparer les données au format attendu
        const data = rowData;
        
        // Remplir le formulaire avec les données
        fillEditForm(form, data);
        
        // Ouvrir le modal
        const modal = new bootstrap.Modal(editModal);
        modal.show();
        return;
    }
    
    // Si aucune donnée n'est passée, essayer de les récupérer via AJAX
    // Vérifier si listId est disponible
    const listIdElement = document.getElementById('listId');
    if (!listIdElement || !listIdElement.value) {
        console.error('ID de liste non trouvé');
        alert('Erreur: ID de liste non trouvé');
        return;
    }
    } catch (error) {
        console.error('Erreur dans la première partie de editRow:', error);
        alert('Une erreur s\'est produite lors de l\'initialisation de l\'édition. Voir la console pour plus de détails.');
        return;
    }
    
    const listId = listIdElement.value;
    console.log('ID de liste récupéré:', listId);
    
    // Afficher un message de chargement
    console.log('Chargement des données de la ligne via AJAX...');
    
    try {
        // Faire une requête AJAX pour récupérer les données complètes de la ligne
        fetch(`/api/lists/${listId}/data/${rowId}`)
            .then(response => {
                console.log('Réponse reçue:', response.status);
                if (!response.ok) {
                    throw new Error(`Erreur HTTP: ${response.status}`);
                }
                return response.json();
            })
        .then(responseData => {
            console.log('Données récupérées via API:', responseData);
            // Utiliser les données de l'API pour remplir le formulaire
            const data = responseData.data || {};
            fillEditForm(form, data);
            
            // Ouvrir le modal
            const modal = new bootstrap.Modal(editModal);
            modal.show();

        })
        .catch(error => {
            console.error('Erreur lors de la récupération des données:', error);
            alert('Erreur lors de la récupération des données de la ligne');
        });
    } catch (error) {
        console.error('Erreur dans la deuxième partie de editRow:', error);
        alert('Une erreur s\'est produite lors de la récupération des données. Voir la console pour plus de détails.');
    }
}

// Fonction pour remplir le formulaire d'édition avec les données
function fillEditForm(form, data) {
    console.log('Remplissage du formulaire avec les données:', data);
    
    // Pour chaque champ du formulaire
    form.querySelectorAll('input[name], select[name], textarea[name]').forEach(input => {
        const fieldName = input.name;
        if (fieldName === 'row_id') return; // Ignorer le champ row_id

        // Récupérer la valeur depuis les données
        const value = data[fieldName] || '';
        console.log('Champ:', fieldName, 'Valeur:', value);
        
        // Si c'est un champ date
        if (input.closest('.flatpickr')) {
            console.log('Initialisation Flatpickr pour:', fieldName);
            // Détruire l'instance Flatpickr existante si elle existe
            if (input._flatpickr) {
                input._flatpickr.destroy();
            }

            // Définir la valeur initiale
            input.value = value;

            // Créer une nouvelle instance Flatpickr
            const fp = flatpickr(input.closest('.flatpickr'), {
                dateFormat: "d/m/Y",
                locale: "fr",
                allowInput: true,
                altInput: true,
                altFormat: "d/m/Y",
                monthSelectorType: "static",
                disableMobile: true,
                wrap: true,
                clickOpens: false,
                onChange: function(selectedDates, dateStr, instance) {
                    console.log('Date sélectionnée:', dateStr);
                }
            });
        } 
        // Si c'est un champ IP
        else if (input.classList.contains('ip-input')) {
            // Détruire l'instance IMask existante si elle existe
            if (input.maskRef) {
                input.maskRef.destroy();
            }

            // Déterminer si c'est une IPv4 ou IPv6
            const isIPv6 = value.includes(':');
            
            // Mettre à jour le type d'IP dans le dropdown
            const dropdown = input.closest('.input-group').querySelector('.dropdown-toggle');
            if (dropdown) {
                dropdown.textContent = isIPv6 ? 'IPv6' : 'IPv4';
            }

            // Créer le masque approprié
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

            // Initialiser IMask
            const mask = IMask(input, maskOptions);
            input.maskRef = mask;

            // Définir la valeur après l'initialisation du masque
            if (value) {
                mask.value = value;
            }
        }
        // Sinon, c'est un champ normal
        else {
            input.value = value;
        }
    });
}

// Fonction pour soumettre le formulaire d'édition
function submitEditRow(event) {
    event.preventDefault();
    console.log('Soumission du formulaire d\'édition');

    // Récupérer le formulaire
    const form = event.target;
    const submitButton = form.querySelector('button[type="submit"]');

    // Éviter la double soumission
    if (form.dataset.submitting === 'true') {
        console.log('Formulaire déjà en cours de soumission');
        return;
    }
    form.dataset.submitting = 'true';

    // Récupérer l'ID de la ligne
    const rowId = form.querySelector('input[name="row_id"]').value;

    // Récupérer les données du formulaire
    const formData = new FormData(form);
    const data = {};
    formData.forEach((value, key) => {
        if (key !== 'row_id') {
            data[key] = value;
        }
    });

    console.log('Données à envoyer:', data);

    // Récupérer le token CSRF
    const csrfMetaTag = document.querySelector('meta[name="csrf-token"]');
    if (!csrfMetaTag) {
        console.error('Token CSRF non trouvé');
        alert('Erreur : Token CSRF manquant');
        form.dataset.submitting = 'false';
        return;
    }
    
    const csrfToken = csrfMetaTag.getAttribute('content');

    // Désactiver le bouton
    submitButton.disabled = true;
    submitButton.textContent = 'Mise à jour...';

    // Configuration de la requête
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

    // Envoyer les données
    fetch(`/api/lists/${listId}/data/${rowId}`, requestOptions)
    .then(response => {
        if (!response.ok) {
            return response.json().then(data => {
                throw new Error(data.error || 'Erreur lors de la mise à jour');
            });
        }
        return response.json();
    })
    .then(data => {
        if (!data.message) {
            throw new Error('Réponse invalide du serveur');
        }

        // Fermer le modal et supprimer le backdrop
        const modalElement = document.getElementById('editRowModal');
        const modal = bootstrap.Modal.getInstance(modalElement);
        if (modal) {
            modal.hide();
            // S'assurer que le backdrop est supprimé
            setTimeout(() => {
                // Supprimer manuellement la classe modal-backdrop et le style overflow
                const backdrop = document.querySelector('.modal-backdrop');
                if (backdrop) {
                    backdrop.remove();
                }
                // Rétablir le défilement normal de la page
                document.body.classList.remove('modal-open');
                document.body.style.overflow = '';
                document.body.style.paddingRight = '';
            }, 300);
        }

        // Mettre à jour la ligne dans le tableau
        return fetch(`/api/lists/${listId}/data/${rowId}`);
    })
    .then(response => {
        if (!response.ok) {
            throw new Error('Erreur lors de la récupération des données mises à jour');
        }
        return response.json();
    })
    .then(rowData => {
        if (!rowData || !rowData.data) {
            throw new Error('Les données de la ligne sont invalides');
        }

        // Trouver la ligne dans le tableau
        const row = document.querySelector(`tr[data-row-id="${rowId}"]`);
        if (!row) {
            console.error('Ligne non trouvée avec tr[data-row-id]');
            
            // Essayer de trouver la ligne via la case à cocher
            const checkbox = document.querySelector(`input.row-checkbox[data-row-id="${rowId}"]`);
            if (checkbox) {
                const checkboxRow = checkbox.closest('tr');
                if (checkboxRow) {
                    console.log('Ligne trouvée via la case à cocher');
                    updateTableRow(checkboxRow, rowData.data);
                } else {
                    console.error('Impossible de trouver la ligne même via la case à cocher');
                    throw new Error('Ligne non trouvée');
                }
            } else {
                console.error('Case à cocher non trouvée');
                throw new Error('Ligne non trouvée');
            }
        } else {
            console.log('Ligne trouvée directement avec tr[data-row-id]');
            updateTableRow(row, rowData.data);
        }
    })
    .catch(error => {
        console.error('Error:', error);
        alert(error.message || 'Erreur lors de la mise à jour');
    })
    .finally(() => {
        // Réactiver le bouton et le formulaire
        submitButton.disabled = false;
        submitButton.textContent = 'Mettre à jour';
        form.dataset.submitting = 'false';
    });
}

// Fonction pour mettre à jour une ligne dans le tableau
function updateTableRow(row, data) {
    console.log('Mise à jour de la ligne avec les données:', data);
    
    try {
        // Utiliser l'API DataTables pour mettre à jour la ligne
        const dataTable = $('#dataTable').DataTable();
        const rowNode = $(row);
        
        if (!rowNode.length) {
            console.error('Ligne non trouvée pour la mise à jour');
            return;
        }
        
        // Vérifier si la première colonne est une case à cocher
        const hasCheckbox = document.querySelector('#dataTable thead th input[type="checkbox"]') !== null;
        
        // Récupérer l'ordre des colonnes depuis les en-têtes du tableau
        const headers = Array.from(document.querySelectorAll('#dataTable thead th'));
        // Exclure la première colonne (checkbox) si elle existe et la dernière colonne (actions) si elle existe
        const startIndex = hasCheckbox ? 1 : 0;
        const endIndex = document.querySelector('#dataTable thead th:last-child').textContent.trim() === 'Actions' ? -1 : undefined;
        const dataHeaders = headers.slice(startIndex, endIndex);
        
        console.log('En-têtes de données:', dataHeaders.map(h => h.textContent.trim()));
        
        // Méthode 1: Mise à jour directe des cellules DOM
        dataHeaders.forEach((header, index) => {
            const columnName = header.textContent.trim();
            const cellIndex = startIndex + index; // Ajuster l'index en fonction de la présence de la case à cocher
            const cellNode = rowNode.find('td').eq(cellIndex);
            
            console.log(`Mise à jour de la cellule ${cellIndex} (${columnName}) avec la valeur:`, data[columnName]);
            
            if (cellNode.length) {
                // Mettre à jour le contenu de la cellule
                cellNode.text(data[columnName] || '');
            } else {
                console.error(`Cellule ${cellIndex} (${columnName}) non trouvée`);
            }
        });
        
        // Méthode 2: Mise à jour via l'API DataTables
        // Préparer un tableau de données pour DataTables
        const rowDataArray = [];
        
        // Ajouter la case à cocher comme première cellule si nécessaire
        if (hasCheckbox) {
            rowDataArray.push(`<input type="checkbox" class="row-checkbox" data-row-id="${row.getAttribute('data-row-id')}">`); 
        }
        
        // Ajouter les cellules de données dans l'ordre des colonnes
        dataHeaders.forEach(header => {
            const columnName = header.textContent.trim();
            rowDataArray.push(data[columnName] || '');
        });
        
        // Ajouter les boutons d'action comme dernière cellule si la colonne Actions existe
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
        
        // Mettre à jour la ligne dans DataTables
        const dtRow = dataTable.row(rowNode);
        dtRow.data(rowDataArray);
        dtRow.invalidate();
        dtRow.draw(false);
        
        // Mettre à jour les attributs data-row-data des boutons d'édition
        setTimeout(() => {
            const newEditButton = $(row).find('.edit-row-btn');
            if (newEditButton.length) {
                newEditButton.attr('data-row-data', JSON.stringify(data));
                console.log('Attribut data-row-data mis à jour avec:', JSON.stringify(data));
                
                // Réinitialiser les gestionnaires d'événements pour les boutons d'édition
                initializeEditButtons();
            }
        }, 100);
        
        console.log('Ligne mise à jour avec succès via DataTables API');
        
        // Afficher une notification temporaire de succès
        if (typeof showSuccess === 'function') {
            showSuccess('Ligne mise à jour avec succès');
        } else {
            console.log('Fonction showSuccess non disponible');
        }
    } catch (error) {
        console.error('Erreur lors de la mise à jour de la ligne:', error);
        if (typeof showError === 'function') {
            showError('Erreur lors de la mise à jour de la ligne. Veuillez rafraîchir la page.');
        } else {
            console.log('Fonction showError non disponible');
        }
    }
}

// Fonction pour formater les dates
function formatDate(dateStr) {
    if (!dateStr) return '';
    
    try {
        // Convertir la chaîne en objet Date
        const date = new Date(dateStr);
        
        // Vérifier si la date est valide
        if (isNaN(date.getTime())) {
            console.warn('Date invalide:', dateStr);
            return dateStr;
        }
        
        // Formater la date en format français (JJ/MM/AAAA)
        const day = String(date.getDate()).padStart(2, '0');
        const month = String(date.getMonth() + 1).padStart(2, '0'); // Les mois commencent à 0
        const year = date.getFullYear();
        
        return `${day}/${month}/${year}`;
    } catch (error) {
        console.error('Erreur lors du formatage de la date:', error);
        return dateStr;
    }
}

// Fonction pour initialiser Flatpickr sur un champ date
function initializeDatePicker(wrapper) {
    console.log('Initialisation de Flatpickr pour le wrapper:', wrapper);
    
    const input = wrapper.querySelector('[data-input]');
    if (!input) {
        console.error('Input non trouvé dans le wrapper');
        return;
    }

    // Détruire l'instance existante si elle existe
    if (input._flatpickr) {
        input._flatpickr.destroy();
    }
    
    // Créer une nouvelle instance
    const fp = flatpickr(wrapper, {
        dateFormat: "d/m/Y",
        locale: "fr",
        allowInput: true,
        altInput: true,
        altFormat: "d/m/Y",
        monthSelectorType: "static",
        disableMobile: true,
        wrap: true,
        clickOpens: false,
        onChange: function(selectedDates, dateStr, instance) {
            console.log('Date sélectionnée:', dateStr);
        }
    });

    // Définir la valeur manuellement si nécessaire
    const defaultDate = wrapper.querySelector('[data-default-date]');
    if (defaultDate) {
        const dateStr = defaultDate.getAttribute('data-default-date');
        if (dateStr) {
            input.value = dateStr;
        }
    }

    return fp;
}

// Fonction pour initialiser les plugins sur un modal
function initializeModalPlugins(modalElement) {
    if (!modalElement) return;

    // Initialiser les gestionnaires pour les champs IP
    modalElement.querySelectorAll('.ip-input').forEach(input => {
        const dropdown = input.closest('.input-group').querySelector('.dropdown-toggle');
        const dropdownItems = input.closest('.input-group').querySelectorAll('.ip-type');

        dropdownItems.forEach(item => {
            item.addEventListener('click', (e) => {
                e.preventDefault();
                const type = e.target.dataset.type;
                dropdown.textContent = type === 'ipv4' ? 'IPv4' : 'IPv6';
                input.placeholder = type === 'ipv4' ? 
                    'ex: 192.168.1.1 ou 192.168.1.0/24' : 
                    'ex: 2001:db8::1 ou 2001:db8::/64';
            });
        });
    });
}

// Fonction pour supprimer une ligne
function deleteRow(rowId) {
    if (!confirm('Êtes-vous sûr de vouloir supprimer cette ligne ?')) {
        return;
    }

    // Récupérer le token CSRF
    const csrfMetaTag = document.querySelector('meta[name="csrf-token"]');
    if (!csrfMetaTag) {
        console.error('Token CSRF non trouvé');
        alert('Erreur : Token CSRF manquant');
        return;
    }
    
    const csrfToken = csrfMetaTag.getAttribute('content');

    // Configuration de la requête
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

    // Envoyer la requête de suppression
    fetch(`/api/lists/${listId}/data/${rowId}`, requestOptions)
    .then(response => {
        if (!response.ok) {
            return response.json().then(data => {
                throw new Error(data.error || 'Erreur lors de la suppression');
            });
        }
        return response.json();
    })
    .then(data => {
        if (data.message) {
            // Supprimer la ligne du tableau en utilisant l'API DataTables
            const dataTable = $('#dataTable').DataTable();
            
            // Trouver la ligne dans DataTables
            const rowToRemove = $(`tr[data-row-id="${rowId}"]`);
            if (rowToRemove.length) {
                // Supprimer la ligne via DataTables API
                dataTable.row(rowToRemove).remove().draw();
                console.log('Ligne supprimée avec succès via DataTables API');
            } else {
                // Si la ligne n'est pas trouvée avec data-row-id, essayer avec la case à cocher
                const checkbox = $(`input.row-checkbox[data-row-id="${rowId}"]`);
                if (checkbox.length) {
                    const checkboxRow = checkbox.closest('tr');
                    if (checkboxRow.length) {
                        dataTable.row(checkboxRow).remove().draw();
                        console.log('Ligne supprimée avec succès via case à cocher');
                    } else {
                        console.error('Impossible de trouver la ligne même via la case à cocher');
                    }
                } else {
                    console.error('Case à cocher non trouvée');
                }
            }
        } else {
            throw new Error(data.error || 'Erreur lors de la suppression');
        }
    })
    .catch(error => {
        console.error('Error:', error);
        alert(error.message || 'Erreur lors de la suppression');
    });
}

// Fonction pour initialiser IMask pour les IPs
function initializeIPMask(input) {
    let currentMask = null;

    function updateMask(type) {
        if (currentMask) {
            currentMask.destroy();
        }

        currentMask = type === 'ipv6' ? createIPv6Mask(input) : createIPv4Mask(input);
    }

    // Initialiser avec IPv4 par défaut
    updateMask('ipv4');

    // Gérer le changement de type d'IP
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
                'ex: 2001:db8::1 ou 2001:db8::/64' : 
                'ex: 192.168.1.1 ou 192.168.1.0/24';
        });
    });
}

function createIPv4Mask(input) {
    return IMask(input, {
        mask: function (value) {
            // Fonction pour créer un pattern pour un octet (0-255)
            const octetPattern = /^[0-9]{1,3}$/;
            
            // Diviser l'IP en octets
            const parts = value.split('.');
            const hasCIDR = value.includes('/');
            
            // Valider chaque octet
            parts.forEach((part, index) => {
                if (index < 4 && part) {  // Les 4 premiers octets
                    const num = parseInt(part);
                    if (!octetPattern.test(part) || num < 0 || num > 255) {
                        return false;
                    }
                }
            });
            
            // Si on a un CIDR, valider le masque
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
            // Formater l'IP correctement
            const parts = value.split('.');
            const formattedParts = parts.map((part, index) => {
                if (index < 4) {  // Les 4 premiers octets
                    const num = parseInt(part);
                    return isNaN(num) ? '' : num.toString();
                }
                return part;  // Pour le CIDR
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
            
            // Valider chaque segment hexadécimal
            for (let i = 0; i < parts.length; i++) {
                const part = parts[i];
                if (i < 8) {  // Les 8 segments de l'IPv6
                    if (part && !/^[0-9A-Fa-f]{1,4}$/.test(part)) {
                        return false;
                    }
                } else if (hasCIDR) {  // Le masque CIDR
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

// Fonction pour initialiser DataTables
function initializeDataTables() {
    const dataTable = $('#dataTable');
    if (dataTable.length) {
        // Déterminer la langue AVANT l'initialisation
        const langMap = { fr: 'fr-FR', en: 'en-US' };
        const langCode = window.currentLanguage && langMap[window.currentLanguage] ? langMap[window.currentLanguage] : 'en-US';
        dataTable.DataTable({
            dom: '<"row"<"col-sm-6"l><"col-sm-6"f>>rt<"row justify-content-center"<"col-auto"p>>i',
            language: {
                url: `/static/js/datatables/i18n/${langCode}.json`
            },
            drawCallback: function() {
                console.log('DataTable redessiné');
                initializeEditButtons();
            },
            initComplete: function() {
                console.log('DataTable initialisé');
                if (!multipleSelectionInitialized) {
                    setupMultipleSelection();
                }
            }
        });
    }
}

// Initialisation quand le DOM est chargé
document.addEventListener('DOMContentLoaded', function() {
    console.log('JavaScript chargé et initialisé');
    
    // Initialiser DataTables
    initializeDataTables();
    
    // Initialiser les plugins sur les modaux
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

    // Initialiser IMask pour les IPs
    const ipInputs = document.querySelectorAll('.ip-input');
    ipInputs.forEach(input => {
        initializeIPMask(input);
    });

    // Ajouter les gestionnaires d'événements pour les formulaires
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

// Fonction pour réinitialiser les cases à cocher
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

// Fonction pour mettre à jour l'affichage du bouton de suppression
function updateDeleteButtonVisibility() {
    const deleteSelectedBtn = document.getElementById('deleteSelectedBtn');
    if (!deleteSelectedBtn) return;
    
    const selectedCount = document.querySelectorAll('#dataTable tbody .row-checkbox:checked').length;
    console.log('Nombre de cases à cocher sélectionnées:', selectedCount);
    
    if (selectedCount > 0) {
        deleteSelectedBtn.style.display = 'inline-block';
        deleteSelectedBtn.textContent = `Supprimer (${selectedCount})`;
    } else {
        deleteSelectedBtn.style.display = 'none';
    }
}

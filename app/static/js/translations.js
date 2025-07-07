// JavaScript translation function
window._ = function(text) {
    // If translations object exists, try to get the translation
    if (window.translations && window.translations[text]) {
        return window.translations[text];
    }
    // Return the original text if no translation is found
    return text;
};

// Translations will be injected here by the template
window.translations = {};

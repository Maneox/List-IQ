// JavaScript translation function
window._ = function(text) {
    // If translations object exists, try to get the translation
    if (window.translations && window.translations[text]) {
        return window.translations[text];
    }
    // Return the original text if no translation is found
    return text;
};

// Translations are injected by the template js_translations.html
// No need to initialize here

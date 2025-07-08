// JavaScript translation function
window._ = function(text) {
    // If translations object exists, try to get the translation
    if (window.translations && window.translations[text]) {
        return window.translations[text];
    }
    // Return the original text if no translation is found
    return text;
};

// String interpolation function for translations with parameters
window.interpolate = function(text, params) {
    if (!params || !params.length) return text;
    
    // Replace %s placeholders with parameters
    if (text.includes('%s')) {
        let result = text;
        for (const param of params) {
            result = result.replace('%s', param);
        }
        return result;
    }
    
    // Support for numbered placeholders like %1$s, %2$s
    return text.replace(/%(\d+)\$s/g, function(match, number) {
        return typeof params[number - 1] !== 'undefined' ? params[number - 1] : match;
    });
};

// Translations are injected by the template js_translations.html
// No need to initialize here

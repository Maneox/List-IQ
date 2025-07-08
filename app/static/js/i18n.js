/**
 * Internationalization (i18n) helper script.
 * This script loads translation files and provides a function to get translated strings.
 */

// Global object to hold the loaded translations.
window.translations = {};

/**
 * Asynchronously loads a translation file for a given language.
 * The translations are stored in the global `window.translations` object.
 * 
 * @param {string} lang - The language code (e.g., 'fr', 'en').
 */
async function loadTranslations(lang) {
    // Map app language codes to translation file names.
    const langMap = {
        fr: 'fr-FR',
        en: 'en-US'
    };
    const langFile = langMap[lang] || 'en-US'; // Default to English.

    try {
        const response = await fetch(`/static/json/${langFile}.json`);
        if (!response.ok) {
            console.error(`Could not load translation file: ${langFile}`);
            // Fallback to English to ensure the UI has text.
            if (langFile !== 'en-US') { 
                await loadTranslations('en');
            }
            return;
        }
        window.translations = await response.json();
        console.log(`Translations successfully loaded for ${lang}.`);
    } catch (error) {
        console.error('Error loading or parsing translation file:', error);
    }
}

/**
 * Gets a translated string for a given key.
 * Supports nested keys (e.g., 'users.delete_confirm').
 * Supports placeholder replacement (e.g., t('key', { count: 5 })).
 * 
 * @param {string} key - The key of the translation string.
 * @param {object} [params={}] - An object with placeholder values to replace.
 * @returns {string} The translated string, or the key itself if not found.
 */
function t(key, params = {}) {
    const keys = key.split('.');
    let text = keys.reduce((obj, i) => (obj ? obj[i] : null), window.translations);

    if (text) {
        // Replace placeholders like {count} with their values.
        Object.keys(params).forEach(param => {
            text = text.replace(new RegExp(`{${param}}`, 'g'), params[param]);
        });
    } else {
        console.warn(`Translation not found for key: ${key}`);
    }

    return text || key; // Return the key as a fallback.
}

// Immediately invoked function to load translations as soon as possible.
(async () => {
    // `window.currentLanguage` is set in the base template from the server.
    const lang = window.currentLanguage || 'en';
    await loadTranslations(lang);
})();

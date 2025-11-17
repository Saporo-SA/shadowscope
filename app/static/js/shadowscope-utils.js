/**
 * ShadowScope Frontend Utilities
 * Centralized utility functions to eliminate code duplication across templates
 */

(function() {
    'use strict';

    // Initialize utilities namespace
    if (!window.ShadowScopeUtils) {
        window.ShadowScopeUtils = {};
    }

    /**
     * Initialize dynamic styling with MutationObserver
     * Applies styles to dynamically created elements
     */
    window.ShadowScopeUtils.initDynamicStyling = function() {
        function styleElements() {
            document.querySelectorAll('.fw-semibold').forEach(el => {
                el.classList.add('text-white');
            });
            
            document.querySelectorAll('.member-item small').forEach(el => {
                el.style.color = 'var(--primary-1)';
            });
            
            document.querySelectorAll('.user-item small').forEach(el => {
                el.style.color = 'var(--primary-3)';
            });
        }
        
        // Apply styles initially
        styleElements();
        
        // Set up MutationObserver to catch dynamically created elements
        const observer = new MutationObserver(function(mutations) {
            styleElements();
        });
        
        // Start observing the DOM for changes
        observer.observe(document.body, { 
            childList: true, 
            subtree: true 
        });
    };

    /**
     * Show loading state on a button
     * @param {HTMLElement} buttonElement - The button element to show loading state on
     * @returns {string} Original button content
     */
    window.ShadowScopeUtils.showButtonLoading = function(buttonElement) {
        if (!buttonElement) return null;
        
        const originalContent = buttonElement.innerHTML;
        buttonElement.setAttribute('data-original-content', originalContent);
        
        buttonElement.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span>';
        buttonElement.disabled = true;
        
        return originalContent;
    };

    /**
     * Restore button to original state
     * @param {HTMLElement} buttonElement - The button element to restore
     */
    window.ShadowScopeUtils.restoreButtonState = function(buttonElement) {
        if (!buttonElement) return;
        
        const originalContent = buttonElement.getAttribute('data-original-content');
        if (originalContent) {
            buttonElement.innerHTML = originalContent;
        }
        buttonElement.disabled = false;
    };

    /**
     * Standardized API request with consistent error handling
     * @param {string} url - The URL to fetch
     * @param {Object} options - Fetch options (method, body, etc.)
     * @returns {Promise} Promise that resolves with parsed JSON response
     */
    window.ShadowScopeUtils.apiRequest = async function(url, options = {}) {
        const defaultOptions = {
            credentials: 'same-origin',
            headers: {
                'Content-Type': 'application/json'
            }
        };

        const mergedOptions = {
            ...defaultOptions,
            ...options,
            headers: {
                ...defaultOptions.headers,
                ...(options.headers || {})
            }
        };

        try {
            const response = await fetch(url, mergedOptions);
            
            // Check if redirect to login page
            if (response.redirected) {
                throw new Error('Redirected to: ' + response.url);
            }
            
            // Get the content type
            const contentType = response.headers.get('content-type');
            
            // Parse response
            const text = await response.text();
            
            // If it's JSON, parse it
            if (contentType && contentType.includes('application/json')) {
                try {
                    const data = JSON.parse(text);
                    return { ...data, status: response.status, ok: response.ok };
                } catch (e) {
                    throw new Error('Response claimed to be JSON but failed to parse');
                }
            } else {
                // Not JSON, show more context about the response
                const firstLine = text.split('\n')[0];
                throw new Error(`Server returned non-JSON response: ${firstLine}`);
            }
        } catch (error) {
            // Enhance error with useful information
            if (error.message === 'Failed to fetch') {
                throw new Error('Connection error: Unable to connect to the server. Please check your internet connection.');
            } else if (error.message.includes('Server returned HTML')) {
                throw new Error('Your session may have expired. Please log in again.');
            } else {
                throw error;
            }
        }
    };

    /**
     * Show notification using unified notification system
     * @param {string} message - The notification message
     * @param {boolean|string} typeOrIsError - Either boolean (isError) or string type ('success', 'error', 'warning', 'info')
     */
    window.ShadowScopeUtils.showNotification = function(message, typeOrIsError = false) {
        if (window.ShadowScopeNotifications) {
            let type = 'success';
            if (typeof typeOrIsError === 'boolean') {
                type = typeOrIsError ? 'error' : 'success';
            } else {
                type = typeOrIsError || 'success';
            }
            window.ShadowScopeNotifications.show(message, type);
        } else {
            alert(message);
        }
    };

    /**
     * Show status notification (alias for showNotification with type)
     * @param {string} message - The notification message
     * @param {string} type - Notification type ('success', 'error', 'warning', 'info')
     */
    window.ShadowScopeUtils.showStatus = function(message, type = 'success') {
        window.ShadowScopeUtils.showNotification(message, type);
    };

    /**
     * Initialize search functionality
     * @param {Object} config - Configuration object
     * @param {string} config.inputId - ID of the search input element
     * @param {string} config.itemSelector - CSS selector for items to filter
     * @param {Array<string>} config.searchFields - Array of CSS selectors for fields to search within each item
     */
    window.ShadowScopeUtils.initSearch = function(config) {
        const { inputId, itemSelector, searchFields } = config;
        const searchInput = document.getElementById(inputId);
        
        if (!searchInput) {
            console.warn(`Search input with ID "${inputId}" not found`);
            return;
        }
        
        searchInput.addEventListener('input', function(e) {
            const searchTerm = e.target.value.toLowerCase();
            
            document.querySelectorAll(itemSelector).forEach(item => {
                let matches = false;
                
                searchFields.forEach(selector => {
                    const element = item.querySelector(selector);
                    if (element) {
                        const text = element.textContent.toLowerCase();
                        if (text.includes(searchTerm)) {
                            matches = true;
                        }
                    }
                });
                
                item.style.display = matches ? '' : 'none';
            });
        });
    };

    // Auto-initialize dynamic styling when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function() {
            window.ShadowScopeUtils.initDynamicStyling();
        });
    } else {
        window.ShadowScopeUtils.initDynamicStyling();
    }

})();


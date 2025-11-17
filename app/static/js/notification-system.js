/**
 * ShadowScope Unified Notification System
 * Provides consistent notification experience across the entire application
 */

class ShadowScopeNotificationSystem {
    constructor() {
        this.container = null;
        this.init();
    }

    init() {
        // Create notification container if it doesn't exist
        if (!document.getElementById('shadowscope-notification-container')) {
            this.createContainer();
        }
        this.container = document.getElementById('shadowscope-notification-container');
    }

    createContainer() {
        const container = document.createElement('div');
        container.id = 'shadowscope-notification-container';
        container.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            z-index: 9999;
            max-width: 400px;
            pointer-events: none;
        `;
        document.body.appendChild(container);
    }

    /**
     * Show a notification
     * @param {string} message - The notification message
     * @param {string} type - Notification type: 'success', 'error', 'warning', 'info'
     * @param {number} duration - Auto-hide duration in milliseconds (default: 5000)
     */
    show(message, type = 'info', duration = 5000) {
        const notification = this.createNotification(message, type);
        this.container.appendChild(notification);

        // Animate in
        requestAnimationFrame(() => {
            notification.style.opacity = '1';
            notification.style.transform = 'translateX(0)';
        });

        // Auto-hide
        if (duration > 0) {
            setTimeout(() => {
                this.hide(notification);
            }, duration);
        }

        return notification;
    }

    hide(notification) {
        notification.style.opacity = '0';
        notification.style.transform = 'translateX(100%)';
        notification.addEventListener('transitionend', () => {
            notification.remove();
        }, { once: true });
    }

    createNotification(message, type) {
        const notification = document.createElement('div');
        notification.className = `shadowscope-notification alert alert-${type} alert-dismissible fade`;
        notification.setAttribute('role', 'alert');
        
        // Enhanced styles with better colors and visibility
        let backgroundColor = 'rgba(30, 30, 35, 0.98)';
        let borderColor = 'var(--primary-1)';
        let textColor = 'var(--white)';
        
        switch (type) {
            case 'success':
                backgroundColor = 'rgba(60, 207, 145, 0.15)';
                borderColor = 'var(--accent-2)';
                textColor = 'var(--white)';
                break;
            case 'error':
                backgroundColor = 'rgba(255, 113, 91, 0.15)';
                borderColor = 'var(--critical)';
                textColor = 'var(--white)';
                break;
            case 'warning':
                backgroundColor = 'rgba(255, 147, 79, 0.15)';
                borderColor = 'var(--primary-2)';
                textColor = 'var(--white)';
                break;
            case 'info':
                backgroundColor = 'rgba(76, 161, 255, 0.15)';
                borderColor = 'var(--primary-4)';
                textColor = 'var(--white)';
                break;
        }
        
        notification.style.cssText = `
            opacity: 0;
            transform: translateX(100%);
            transition: opacity 0.5s ease-out, transform 0.5s ease-out;
            margin-bottom: 10px;
            pointer-events: auto;
            background-color: ${backgroundColor};
            border: 2px solid ${borderColor};
            border-left: 4px solid ${borderColor};
            color: ${textColor};
            backdrop-filter: blur(10px);
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4);
            border-radius: 8px;
            padding: 1rem;
            min-width: 320px;
        `;

        let iconClass = '';
        let iconColor = '';
        switch (type) {
            case 'success':
                iconClass = 'bi-check-circle-fill';
                iconColor = 'var(--accent-2)';
                break;
            case 'error':
                iconClass = 'bi-exclamation-circle-fill';
                iconColor = 'var(--critical)';
                break;
            case 'warning':
                iconClass = 'bi-exclamation-triangle-fill';
                iconColor = 'var(--primary-2)';
                break;
            case 'info':
                iconClass = 'bi-info-circle-fill';
                iconColor = 'var(--primary-4)';
                break;
            default:
                iconClass = 'bi-info-circle-fill';
                iconColor = 'var(--primary-4)';
        }

        notification.innerHTML = `
            <div class="d-flex align-items-start">
                <i class="bi ${iconClass} me-3" style="color: ${iconColor}; font-size: 1.5rem; flex-shrink: 0;"></i>
                <div style="flex: 1; font-size: 0.9rem; line-height: 1.5;">${message}</div>
                <button type="button" class="btn-close btn-close-white ms-3" data-bs-dismiss="alert" aria-label="Close" style="opacity: 0.6; flex-shrink: 0;"></button>
            </div>
        `;

        return notification;
    }

    success(message, duration = 5000) {
        return this.show(message, 'success', duration);
    }

    error(message, duration = 7000) {
        return this.show(message, 'error', duration);
    }

    warning(message, duration = 6000) {
        return this.show(message, 'warning', duration);
    }

    info(message, duration = 5000) {
        return this.show(message, 'info', duration);
    }
}

// Global notification system instance - initialize when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
    if (!window.ShadowScopeNotifications) {
        window.ShadowScopeNotifications = new ShadowScopeNotificationSystem();
    }
});

// Also initialize immediately if DOM is already loaded
if (document.readyState === 'loading') {
    // DOM is still loading, wait for DOMContentLoaded
} else {
    // DOM is already loaded
    if (!window.ShadowScopeNotifications) {
        window.ShadowScopeNotifications = new ShadowScopeNotificationSystem();
    }
}

// Convenience functions for backward compatibility with fallback
window.showNotification = (message, isError = false, duration = 5000) => {
    if (window.ShadowScopeNotifications) {
        return window.ShadowScopeNotifications.show(message, isError ? 'error' : 'success', duration);
    } else {
        // Fallback to alert if system not ready
        alert(message);
    }
};

window.showStatus = (message, type = 'success', duration = 5000) => {
    if (window.ShadowScopeNotifications) {
        return window.ShadowScopeNotifications.show(message, type, duration);
    } else {
        // Fallback to alert if system not ready
        alert(message);
    }
};

// Export for module systems
if (typeof module !== 'undefined' && module.exports) {
    module.exports = ShadowScopeNotificationSystem;
}
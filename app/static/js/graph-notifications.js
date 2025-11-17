class GraphNotificationsSystem {
    constructor() {
        this.isTabActive = true;
        // Load already shown alerts from sessionStorage
        const storedAlerts = sessionStorage.getItem('shownNotificationAlerts');
        this.processedAlerts = storedAlerts ? new Set(JSON.parse(storedAlerts)) : new Set();
        this.init();
    }
    
    saveProcessedAlerts() {
        // Save to sessionStorage
        sessionStorage.setItem('shownNotificationAlerts', JSON.stringify(Array.from(this.processedAlerts)));
    }

    init() {
        this.startPolling();
        this.setupTabVisibilityTracking();
        
        if (window.location.pathname.includes('/notifications')) {
            if (document.readyState === 'loading') {
                document.addEventListener('DOMContentLoaded', () => {
                    this.updateNotificationsDisplay();
                });
            } else {
                this.updateNotificationsDisplay();
            }
        }
    }
    
    setupTabVisibilityTracking() {
        document.addEventListener('visibilitychange', () => {
            this.isTabActive = !document.hidden;
        });
        
        window.addEventListener('focus', () => {
            this.isTabActive = true;
            this.clearPersistentNotifications();
        });
        
        window.addEventListener('blur', () => {
            this.isTabActive = false;
        });
    }
    
    clearPersistentNotifications() {
        // Clear notifications that persist when tab is inactive
        if (window.ShadowScopeNotifications) {
            const container = document.getElementById('notification-container');
            if (container) {
                const persistentNotifs = container.querySelectorAll('.notification-item[data-duration="0"]');
                persistentNotifs.forEach(notif => notif.remove());
            }
        }
    }
    
    startPolling() {
        // Poll for new notifications every 3 seconds
        setInterval(() => {
            this.checkForNewNotifications();
        }, 3000);
        
        // Initial check
        this.checkForNewNotifications();
    }
    
    async checkForNewNotifications() {
        try {
            const response = await fetch('/api/notifications/latest');
            const data = await response.json();
            
            if (data.success && data.notifications) {
                data.notifications.forEach(notification => {
                    // Show alert only once per notification
                    if (!this.processedAlerts.has(notification.id)) {
                        this.showRealTimeAlert(notification);
                        this.processedAlerts.add(notification.id);
                        
                        // Keep only last 100 alert IDs in memory
                        if (this.processedAlerts.size > 100) {
                            const alertsArray = Array.from(this.processedAlerts);
                            this.processedAlerts = new Set(alertsArray.slice(-100));
                        }
                    }
                });
                
                // Save to sessionStorage after processing
                this.saveProcessedAlerts();
                
                // Update display if on notifications page
                if (window.location.pathname.includes('/notifications')) {
                    this.updateNotificationsDisplay();
                }
            }
        } catch (error) {
            // Silently fail - don't spam console
        }
    }
    
    showRealTimeAlert(notification) {
        if (!window.ShadowScopeNotifications) return;
        
        const title = notification.title || notification.subtitle || 'Resource Activity';
        const changeType = notification.change_type || notification.changeType || 'Activity';
        
        // Determine notification type and icon based on change type
        let notificationType = 'info';
        let icon = '🔔';
        
        if (changeType.toLowerCase() === 'created') {
            notificationType = 'success';
            icon = '✅';
        } else if (changeType.toLowerCase() === 'updated') {
            notificationType = 'warning';
            icon = '✏️';
        }
        
        // Smart duration: 15 seconds if tab is active, persistent if inactive
        const duration = this.isTabActive ? 15000 : 0;
        
        // Enhanced message with better formatting
        const message = `
            <div style="display: flex; flex-direction: column; gap: 0.25rem;">
                <div style="font-weight: 600; font-size: 0.9rem;">${title}</div>
                <div style="font-size: 0.75rem; opacity: 0.8;">${changeType.toUpperCase()}</div>
            </div>
        `;
        
        window.ShadowScopeNotifications.show(
            message,
            notificationType,
            duration,
            {
                icon: icon,
                tag: 'graph-notification'
            }
        );
    }

    updateNotificationsDisplay() {
        // Update both displays if on notifications page
        const notificationsContainer = document.getElementById('notificationsDisplay');
        const messagesContainer = document.getElementById('messagesDisplay');
        
        if (notificationsContainer) {
            this.renderNotificationsList(notificationsContainer);
        }
        
        if (messagesContainer) {
            this.renderMessagesList(messagesContainer);
        }
    }

    async renderNotificationsList(container) {
        try {
            const response = await fetch('/api/notifications/latest');
            const data = await response.json();
            
            if (!data.success || !data.notifications || data.notifications.length === 0) {
                container.innerHTML = `
                    <div class="text-center text-muted py-4">
                        <i class="bi bi-bell-slash d-block mb-2" style="font-size: 2rem;"></i>
                        <small>No notifications received yet</small>
                    </div>
                `;
                return;
            }

            const html = data.notifications
                .reverse()
                .map((notification) => {
                    const timestamp = new Date(notification.timestamp).toLocaleString();
                    const title = notification.title || 'Unknown Resource';
                    const subtitle = notification.subtitle || '';
                    const changeType = notification.change_type || notification.changeType || 'Unknown Change';
                    
                    // Format content similar to messages
                    let contentHtml = '';
                    if (subtitle) {
                        // Parse subtitle for From/To info (Chat) or Teams/Channel (Teams)
                        if (subtitle.includes(' → ')) {
                            const parts = subtitle.split(' → ');
                            if (parts.length === 2 && !subtitle.includes('Teams:') && !subtitle.includes('Channel:')) {
                                // Chat 1:1
                                contentHtml = `
                                    <div class="notification-card-body">
                                        <div class="message-info-line">
                                            <i class="bi bi-person"></i>
                                            <strong>From:</strong> ${parts[0].trim()}
                                            <strong class="ms-2">To:</strong> ${parts[1].trim()}
                                        </div>
                                        <div class="message-info-line">
                                            <i class="bi bi-clock"></i>
                                            <strong>Received:</strong> ${timestamp}
                                        </div>
                                    </div>
                                `;
                            } else if (subtitle.includes('Teams:') || subtitle.includes('Channel:')) {
                                // Teams channel
                                contentHtml = `
                                    <div class="notification-card-body">
                                        <div class="message-info-line">
                                            <i class="bi bi-arrow-right-circle"></i>
                                            ${subtitle}
                                        </div>
                                        <div class="message-info-line">
                                            <i class="bi bi-clock"></i>
                                            <strong>Received:</strong> ${timestamp}
                                        </div>
                                    </div>
                                `;
                            } else {
                                // Group chat
                                contentHtml = `
                                    <div class="notification-card-body">
                                        <div class="message-info-line">
                                            <i class="bi bi-people"></i>
                                            ${subtitle}
                                        </div>
                                        <div class="message-info-line">
                                            <i class="bi bi-clock"></i>
                                            <strong>Received:</strong> ${timestamp}
                                        </div>
                                    </div>
                                `;
                            }
                        } else {
                            contentHtml = `
                                <div class="notification-card-body">
                                    <div class="message-info-line">
                                        <i class="bi bi-arrow-right-circle"></i>
                                        ${subtitle}
                                    </div>
                                    <div class="message-info-line">
                                        <i class="bi bi-clock"></i>
                                        <strong>Received:</strong> ${timestamp}
                                    </div>
                                </div>
                            `;
                        }
                    } else {
                        // Fallback without subtitle
                        contentHtml = `
                            <div class="notification-card-body">
                                <div class="message-info-line">
                                    <i class="bi bi-clock"></i>
                                    <strong>Received:</strong> ${timestamp}
                                </div>
                                <div class="message-info-line">
                                    <i class="bi bi-key"></i>
                                    <strong>Subscription:</strong> ${notification.subscription_id?.substring(0, 8)}...
                                </div>
                            </div>
                        `;
                    }
                    
                    return `
                        <div class="notification-card">
                            <div class="notification-card-header">
                                <div class="d-flex justify-content-between align-items-center">
                                    <div class="d-flex align-items-center">
                                        <i class="bi bi-bell text-primary me-2"></i>
                                        <strong class="text-primary" style="font-size: 0.8125rem;">${title}</strong>
                                    </div>
                                    <span class="badge bg-${this.getChangeTypeColor(changeType)}" style="font-size: 0.625rem;">${changeType.toUpperCase()}</span>
                                </div>
                            </div>
                            ${contentHtml}
                        </div>
                    `;
                }).join('');

            container.innerHTML = html;
        } catch (error) {
            container.innerHTML = `
                <div class="text-center text-muted py-4">
                    <i class="bi bi-exclamation-triangle d-block mb-2" style="font-size: 2rem;"></i>
                    <small>Error loading notifications</small>
                </div>
            `;
        }
    }
    
    async renderMessagesList(container) {
        try {
            const response = await fetch('/api/messages/latest');
            const data = await response.json();
            
            if (!data.success || !data.messages || data.messages.length === 0) {
                container.innerHTML = `
                    <div class="text-center text-muted py-4">
                        <i class="bi bi-shield-slash d-block mb-2" style="font-size: 2rem;"></i>
                        <small>No messages with keywords detected yet</small>
                    </div>
                `;
                return;
            }

            const html = data.messages
                .reverse()
                .map((message) => {
                    const timestamp = new Date(message.timestamp).toLocaleString();
                    const title = message.title || 'Unknown Message';
                    const subtitle = message.subtitle || '';
                    const messageData = message.message_data;
                    
                    const notificationId = message.notification_id || '';
                    const changeType = notificationId.includes('_created') ? 'created' : 
                                     notificationId.includes('_updated') ? 'updated' : 'unknown';
                    
                    let contentHtml = '';
                    if (message.status === 'fetched' && messageData) {
                        const from = messageData.from?.user?.displayName || messageData.from?.application?.displayName || 'Unknown';
                        const sentTime = messageData.createdDateTime ? new Date(messageData.createdDateTime).toLocaleString() : 'Unknown';
                        const body = messageData.body?.content || 'No content';
                        const contentType = messageData.body?.contentType || 'text';
                        
                        // If subtitle exists (Chat 1:1 or Group), use it. Otherwise show From
                        let fromToLine = '';
                        if (subtitle) {
                            // Parse subtitle to get From/To info
                            if (subtitle.includes(' → ')) {
                                const parts = subtitle.split(' → ');
                                if (parts.length === 2) {
                                    fromToLine = `
                                        <div class="message-info-line">
                                            <i class="bi bi-person"></i>
                                            <strong>From:</strong> ${parts[0].trim()}
                                            <strong class="ms-2">To:</strong> ${parts[1].trim()}
                                        </div>
                                    `;
                                } else {
                                    // Group chat (multiple users)
                                    fromToLine = `
                                        <div class="message-info-line">
                                            <i class="bi bi-people"></i>
                                            ${subtitle}
                                        </div>
                                    `;
                                }
                            } else {
                                // Teams channel or other
                                fromToLine = `
                                    <div class="message-info-line">
                                        <i class="bi bi-arrow-right-circle"></i>
                                        ${subtitle}
                                    </div>
                                `;
                            }
                        } else {
                            // Fallback to just From
                            fromToLine = `
                                <div class="message-info-line">
                                    <i class="bi bi-person"></i>
                                    <strong>From:</strong> ${from}
                                </div>
                            `;
                        }
                        
                        contentHtml = `
                            <div class="notification-card-body">
                                ${fromToLine}
                                <div class="message-info-line">
                                    <i class="bi bi-clock"></i>
                                    <strong>Sent:</strong> ${sentTime}
                                </div>
                                <div class="message-info-line">
                                    <i class="bi bi-chat-left-text"></i>
                                    <strong>Message:</strong> ${this.formatMessageBody(body, contentType)}
                                </div>
                            </div>
                        `;
                    } else if (message.status === 'pending') {
                        contentHtml = `
                            <div class="notification-card-body">
                                <div class="d-flex align-items-center">
                                    <div class="spinner-border spinner-border-sm text-primary me-2" role="status">
                                        <span class="visually-hidden">Loading...</span>
                                    </div>
                                    <small class="text-muted">Loading message...</small>
                                </div>
                            </div>
                        `;
                    } else if (message.status === 'error') {
                        contentHtml = `
                            <div class="notification-card-body">
                                <div class="text-danger">
                                    <i class="bi bi-exclamation-triangle me-2"></i>
                                    <small>Failed to load message</small>
                                </div>
                            </div>
                        `;
                    }
                    
                    // Show Load Context button for Teams and Chats
                    const isTeamsOrChat = message.resource && (message.resource.includes('teams(') || message.resource.includes('chats('));
                    const loadContextBtn = message.status === 'fetched' && isTeamsOrChat ? `
                        <button class="btn btn-sm btn-outline-primary mt-2 load-context-btn" 
                                data-resource="${message.resource}"
                                style="font-size: 0.75rem; padding: 0.25rem 0.5rem;">
                            <i class="bi bi-arrow-left-right me-1"></i>
                            Load Context
                        </button>
                    ` : '';
                    
                    return `
                        <div class="notification-card">
                            <div class="notification-card-header">
                                <div class="d-flex justify-content-between align-items-center">
                                    <div class="d-flex align-items-center">
                                        <i class="bi bi-shield-exclamation text-warning me-2"></i>
                                        <strong class="text-warning" style="font-size: 0.8125rem;">${title}</strong>
                                    </div>
                                    <span class="badge bg-${this.getChangeTypeColor(changeType)}" style="font-size: 0.625rem;">${changeType.toUpperCase()}</span>
                                </div>
                            </div>
                            ${contentHtml}
                            ${loadContextBtn}
                        </div>
                    `;
                }).join('');

            container.innerHTML = html;
            
            // Add event listeners to Load Context buttons
            container.querySelectorAll('.load-context-btn').forEach(btn => {
                btn.addEventListener('click', (e) => this.loadMessageContext(e.target.dataset.resource));
            });
        } catch (error) {
            container.innerHTML = `
                <div class="text-center text-muted py-4">
                    <i class="bi bi-exclamation-triangle d-block mb-2" style="font-size: 2rem;"></i>
                    <small>Error loading messages</small>
                </div>
            `;
        }
    }
    
    async loadMessageContext(resourcePath) {
        try {
            if (window.ShadowScopeNotifications) {
                window.ShadowScopeNotifications.info('Loading message context...');
            }
            
            const response = await fetch('/api/message-context', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    resource_path: resourcePath,
                    before: 10,
                    after: 10
                })
            });
            
            const data = await response.json();
            
            if (data.success) {
                this.displayMessageContext(data);
            } else {
                if (window.ShadowScopeNotifications) {
                    window.ShadowScopeNotifications.error(data.message || 'Failed to load context');
                }
            }
        } catch (error) {
            if (window.ShadowScopeNotifications) {
                window.ShadowScopeNotifications.error('Error loading message context');
            }
        }
    }
    
    renderResourceInfo(contextData) {
        if (contextData.resource_type === 'chat') {
            const chatTypeIcon = contextData.chat_type === 'oneOnOne' ? 'bi-person-fill' : 'bi-people-fill';
            const chatTypeLabel = contextData.chat_type === 'oneOnOne' ? '1:1 Chat' : 'Group Chat';
            return `
                <i class="${chatTypeIcon} me-2" style="color: #3ccf91;"></i>
                <strong style="color: #ffffff;">${chatTypeLabel}:</strong> ${contextData.chat_topic || 'Chat'}
            `;
        } else {
            // Teams
            return `
                <i class="bi bi-building me-2" style="color: #3ccf91;"></i>
                <strong style="color: #ffffff;">Team:</strong> ${contextData.team_name}
                <span class="ms-3"><i class="bi bi-hash me-2" style="color: #3ccf91;"></i><strong style="color: #ffffff;">Channel:</strong> ${contextData.channel_name}</span>
            `;
        }
    }
    
    displayMessageContext(contextData) {
        let contextType, contextIcon, infoText;
        
        if (contextData.is_thread) {
            contextType = 'Thread Context';
            contextIcon = 'bi-chat-right-text';
            const hasParent = contextData.parent_message ? ' (including root message)' : '';
            infoText = `Showing ${contextData.total_before} messages before and ${contextData.total_after} messages after the intercepted reply${hasParent}`;
        } else if (contextData.is_root_message) {
            contextType = 'Root Message + Replies';
            contextIcon = 'bi-chat-square-dots';
            infoText = `This is the root message that started this thread${contextData.total_after > 0 ? ` with ${contextData.total_after} ${contextData.total_after === 1 ? 'reply' : 'replies'}` : ' (no replies yet)'}`;
        } else {
            // Determinar tipo baseado no resource_type e chat_type
            if (contextData.resource_type === 'chat') {
                if (contextData.chat_type === 'oneOnOne') {
                    contextType = '1:1 Message Context';
                    contextIcon = 'bi-person-fill';
                } else {
                    contextType = 'Group Chat Message Context';
                    contextIcon = 'bi-people-fill';
                }
            } else {
                contextType = 'Channel Message Context';
                contextIcon = 'bi-chat-square-text';
            }
            infoText = `Showing ${contextData.total_before} messages before and ${contextData.total_after} messages after`;
        }
        
        const modalHtml = `
            <div class="modal fade" id="messageContextModal" tabindex="-1" aria-hidden="true" style="z-index: 9999;">
                <div class="modal-dialog modal-xl modal-dialog-scrollable">
                    <div class="modal-content" style="background: #1a1d2e; border: 2px solid rgba(255, 113, 91, 0.3); box-shadow: 0 10px 40px rgba(0, 0, 0, 0.8);">
                        <div class="modal-header" style="background: #12141d; border-bottom: 2px solid rgba(255, 113, 91, 0.2); padding: 1.25rem;">
                            <h5 class="modal-title" style="color: #ffffff; font-weight: 600; font-size: 1.1rem;">
                                <i class="bi ${contextIcon} me-2" style="color: #ff715b;"></i>
                                ${contextType}
                            </h5>
                            <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal" style="filter: brightness(1.5);"></button>
                        </div>
                        <div class="modal-body" style="background: #1a1d2e; padding: 1.5rem; max-height: 70vh; overflow-y: auto;">
                            <div class="mb-4" style="background: rgba(255, 113, 91, 0.08); padding: 1rem; border-radius: 8px; border-left: 4px solid #ff715b;">
                                <div style="color: rgba(255, 255, 255, 0.9); font-size: 0.9rem; margin-bottom: 0.5rem;">
                                    ${this.renderResourceInfo(contextData)}
                                </div>
                                <div style="color: rgba(255, 255, 255, 0.8); font-size: 0.875rem;">
                                    <i class="bi bi-info-circle me-2" style="color: #ff934f;"></i>
                                    ${infoText}
                                </div>
                            </div>
                            
                            <div class="context-messages-container">
                                ${this.renderContextMessages(contextData)}
                            </div>
                        </div>
                        <div class="modal-footer" style="background: #12141d; border-top: 2px solid rgba(255, 113, 91, 0.2); padding: 1rem;">
                            <button type="button" class="btn btn-secondary" data-bs-dismiss="modal" style="background: rgba(255, 113, 91, 0.2); border: 1px solid rgba(255, 113, 91, 0.4); color: #ffffff; font-weight: 500;">
                                <i class="bi bi-x-circle me-1"></i> Close
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        `;
        
        const existingModal = document.getElementById('messageContextModal');
        if (existingModal) {
            existingModal.remove();
        }
        
        document.body.insertAdjacentHTML('beforeend', modalHtml);
        
        const modal = new bootstrap.Modal(document.getElementById('messageContextModal'), {
            backdrop: 'static',
            keyboard: true
        });
        modal.show();
        
        // Add custom backdrop styling
        setTimeout(() => {
            const backdrop = document.querySelector('.modal-backdrop');
            if (backdrop) {
                backdrop.style.backgroundColor = 'rgba(0, 0, 0, 0.85)';
                backdrop.style.backdropFilter = 'blur(5px)';
            }
        }, 100);
        
        document.getElementById('messageContextModal').addEventListener('hidden.bs.modal', function() {
            this.remove();
        });
    }
    
    renderContextMessages(contextData) {
        let html = '';
        
        if (contextData.is_root_message) {
            if (contextData.target_message) {
                html += `<div class="context-section mb-4">
                            <h6 style="color: #ffc107; font-size: 0.95rem; font-weight: 700; margin-bottom: 1rem; padding: 0.75rem; background: rgba(255, 193, 7, 0.15); border-radius: 6px; border-left: 4px solid #ffc107;">
                                <i class="bi bi-star-fill me-2"></i>
                                Root Message (Intercepted Notification)
                            </h6>`;
                html += this.renderSingleMessage(contextData.target_message, true);
                html += '</div>';
            }
            return html;
        }
        
        if (contextData.is_thread && contextData.parent_message) {
            html += `<div class="context-section mb-4">
                        <h6 style="color: rgba(60, 207, 145, 0.9); font-size: 0.9rem; font-weight: 600; margin-bottom: 1rem; padding: 0.75rem; background: rgba(60, 207, 145, 0.1); border-radius: 6px; border-left: 4px solid #3ccf91;">
                            <i class="bi bi-chat-square-text me-2"></i>
                            Thread Root Message
                        </h6>`;
            html += this.renderSingleMessage(contextData.parent_message, false);
            html += '</div>';
        }
        
        // Mensagens antes da notificação
        if (contextData.before_messages && contextData.before_messages.length > 0) {
            const label = contextData.is_thread ? 'Previous Replies' : 'Previous Messages';
            html += `<div class="context-section mb-4">
                        <h6 style="color: rgba(255, 255, 255, 0.7); font-size: 0.875rem; font-weight: 600; margin-bottom: 1rem; padding-bottom: 0.5rem; border-bottom: 1px solid rgba(255, 255, 255, 0.1);">
                            <i class="bi bi-arrow-up-circle me-2" style="color: #3ccf91;"></i>
                            ${label} (${contextData.before_messages.length})
                        </h6>`;
            contextData.before_messages.forEach(msg => {
                html += this.renderSingleMessage(msg, false);
            });
            html += '</div>';
        }
        
        // Mensagem target (notificação)
        if (contextData.target_message) {
            const targetLabel = contextData.is_thread ? 'Intercepted Reply (Notification)' : 'Target Message (Intercepted Notification)';
            html += `<div class="context-section mb-4">
                        <h6 style="color: #ffc107; font-size: 0.95rem; font-weight: 700; margin-bottom: 1rem; padding: 0.75rem; background: rgba(255, 193, 7, 0.15); border-radius: 6px; border-left: 4px solid #ffc107;">
                            <i class="bi bi-star-fill me-2"></i>
                            ${targetLabel}
                        </h6>`;
            html += this.renderSingleMessage(contextData.target_message, true);
            html += '</div>';
        }
        
        // Mensagens depois da notificação
        if (contextData.after_messages && contextData.after_messages.length > 0) {
            const label = contextData.is_thread ? 'Following Replies' : 'Following Messages';
            html += `<div class="context-section">
                        <h6 style="color: rgba(255, 255, 255, 0.7); font-size: 0.875rem; font-weight: 600; margin-bottom: 1rem; padding-bottom: 0.5rem; border-bottom: 1px solid rgba(255, 255, 255, 0.1);">
                            <i class="bi bi-arrow-down-circle me-2" style="color: #ff715b;"></i>
                            ${label} (${contextData.after_messages.length})
                        </h6>`;
            contextData.after_messages.forEach(msg => {
                html += this.renderSingleMessage(msg, false);
            });
            html += '</div>';
        }
        
        if (!contextData.is_root_message && !contextData.parent_message && !contextData.before_messages?.length && !contextData.after_messages?.length) {
            html += '<div style="text-align: center; padding: 2rem; color: rgba(255, 255, 255, 0.5);"><i class="bi bi-info-circle me-2"></i>No surrounding messages found</div>';
        }
        
        return html;
    }
    
    renderSingleMessage(msg, isTarget) {
        const from = msg.from?.user?.displayName || 'Unknown';
        const timestamp = msg.createdDateTime ? new Date(msg.createdDateTime).toLocaleString() : 'Unknown';
        const body = msg.body?.content || 'No content';
        const contentType = msg.body?.contentType || 'text';
        
        // Melhorar contraste visual
        const bgClass = isTarget ? 'rgba(255, 193, 7, 0.2)' : 'rgba(255, 255, 255, 0.08)';
        const borderColor = isTarget ? '#ffc107' : 'rgba(255, 255, 255, 0.2)';
        
        let repliesHtml = '';
        if (msg.replies && msg.replies.length > 0) {
            repliesHtml = '<div style="margin-left: 1.5rem; margin-top: 0.75rem; border-left: 3px solid rgba(60, 207, 145, 0.5); padding-left: 1rem;">';
            repliesHtml += `<div style="color: #3ccf91; font-size: 0.75rem; margin-bottom: 0.5rem; font-weight: 600;"><i class="bi bi-reply-fill me-1"></i>${msg.replies.length} ${msg.replies.length === 1 ? 'Reply' : 'Replies'}</div>`;
            
            msg.replies.forEach(reply => {
                const replyFrom = reply.from?.user?.displayName || 'Unknown';
                const replyTimestamp = reply.createdDateTime ? new Date(reply.createdDateTime).toLocaleString() : 'Unknown';
                const replyBody = reply.body?.content || 'No content';
                const replyContentType = reply.body?.contentType || 'text';
                
                repliesHtml += `
                    <div style="background: rgba(60, 207, 145, 0.15); border: 1px solid rgba(60, 207, 145, 0.3); border-radius: 6px; padding: 0.5rem; margin-bottom: 0.5rem;">
                        <div class="d-flex justify-content-between align-items-start mb-1">
                            <div>
                                <i class="bi bi-person me-1" style="color: #3ccf91; font-size: 0.75rem;"></i>
                                <strong style="color: #ffffff; font-size: 0.8125rem;">${replyFrom}</strong>
                            </div>
                            <small style="color: rgba(255, 255, 255, 0.7); font-size: 0.7rem;">
                                <i class="bi bi-clock me-1"></i>${replyTimestamp}
                            </small>
                        </div>
                        <div style="color: rgba(255, 255, 255, 0.9); font-size: 0.8125rem;">
                            ${this.formatMessageBody(replyBody, replyContentType)}
                        </div>
                    </div>
                `;
            });
            
            repliesHtml += '</div>';
        }
        
        return `
            <div class="message-context-card mb-3" style="background: ${bgClass}; border-left: 4px solid ${borderColor}; padding: 0.75rem; border-radius: 6px;">
                <div class="d-flex justify-content-between align-items-start mb-2">
                    <div>
                        <i class="bi bi-person-circle me-2" style="color: #3ccf91; font-size: 1.1rem;"></i>
                        <strong style="color: #ffffff; font-size: 0.95rem;">${from}</strong>
                    </div>
                    <small style="color: rgba(255, 255, 255, 0.7); font-size: 0.75rem;">
                        <i class="bi bi-clock me-1"></i>${timestamp}
                    </small>
                </div>
                <div style="color: rgba(255, 255, 255, 0.95); font-size: 0.9rem; padding-left: 1.75rem; line-height: 1.5;">
                    ${this.formatMessageBody(body, contentType)}
                </div>
                ${repliesHtml}
            </div>
        `;
    }
    
    formatMessageBody(content, contentType) {
        if (!content) return '<em class="text-muted">No content</em>';
        
        if (contentType === 'html') {
            // Strip potentially dangerous HTML tags, keep only safe formatting
            const tempDiv = document.createElement('div');
            tempDiv.innerHTML = content;
            return tempDiv.textContent || tempDiv.innerText || content;
        }
        
        // Plain text - preserve line breaks
        return content.replace(/\n/g, '<br>');
    }
    
    getChangeTypeColor(changeType) {
        const colors = {
            'created': 'success',
            'updated': 'info'
        };
        return colors[changeType] || colors[changeType.toLowerCase()] || 'secondary';
    }
}

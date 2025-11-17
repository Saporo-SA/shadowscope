"""
Notifications routes for Graph API Change Notifications management.
"""

import json
import os
import uuid
from datetime import datetime, timedelta
from flask import (
    Blueprint,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from app.modules.graph_notifications import GraphNotifications
from app.utils.route_helpers import get_user_context, prepare_module_permissions
from app.utils.message_utils import process_message, sort_messages_chronologically

notifications_bp = Blueprint('notifications', __name__)

# File paths for storing notifications
RESULTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'results')
NOTIFICATIONS_FILE = os.path.join(RESULTS_DIR, 'notifications.json')
MESSAGES_FILE = os.path.join(RESULTS_DIR, 'messages.json')

# Ensure results directory exists
os.makedirs(RESULTS_DIR, exist_ok=True)


def load_notifications():
    """Load notifications from file."""
    try:
        if os.path.exists(NOTIFICATIONS_FILE):
            with open(NOTIFICATIONS_FILE, 'r') as f:
                return json.load(f)
    except Exception as e:
        current_app.logger.error(f"Error loading notifications: {str(e)}")
    return []


def save_notifications(notifications):
    """Save notifications to file."""
    try:
        with open(NOTIFICATIONS_FILE, 'w') as f:
            json.dump(notifications, f, indent=2)
    except Exception as e:
        current_app.logger.error(f"Error saving notifications: {str(e)}")


def load_messages():
    """Load messages from file."""
    try:
        if os.path.exists(MESSAGES_FILE):
            with open(MESSAGES_FILE, 'r') as f:
                return json.load(f)
    except Exception as e:
        current_app.logger.error(f"Error loading messages: {str(e)}")
    return []


def save_messages(messages):
    """Save messages to file."""
    try:
        with open(MESSAGES_FILE, 'w') as f:
            json.dump(messages, f, indent=2)
    except Exception as e:
        current_app.logger.error(f"Error saving messages: {str(e)}")


@notifications_bp.route('/notifications')
def notifications():
    """Change Notifications page with Graph API Notifications management."""
    try:
        user_context = get_user_context()
        token_data = user_context.get('token_data', {})
        if not token_data:
            return redirect(url_for('auth.login'))
        
        if 'graph_token' not in session:
            return redirect(url_for('auth.login'))
        
        access = user_context.get('access', {})
        
        module_permissions = prepare_module_permissions('graph_notifications', access) or {}
        
        subscriptions = []
        try:
            notifications_api = GraphNotifications(session['graph_token'])
            subscriptions_result = notifications_api.list_subscriptions()
            
            if subscriptions_result['success']:
                subscriptions = subscriptions_result['data']
        except Exception as e:
            current_app.logger.error(f"Error getting subscriptions: {str(e)}")
            flash(f'Error loading subscriptions: {str(e)}', 'error')
        
        return render_template('notifications/notifications.html', 
                             access=access,
                             module_permissions=module_permissions,
                             subscriptions=subscriptions)
    except Exception as e:
        current_app.logger.error(f"Error in notifications route: {str(e)}")
        flash(f'Error loading notifications page: {str(e)}', 'error')
        return redirect(url_for('dashboard.dashboard'))


@notifications_bp.route('/notifications/create-subscription', methods=['POST'])
def create_subscription():
    """Create a new Graph API subscription."""
    user_context = get_user_context()
    token_data = user_context.get('token_data', {})
    if not token_data:
        return redirect(url_for('auth.login'))
    
    access = user_context.get('access', {})
    
    if not access.get('graph_notifications', {}).get('base', False):
        flash('Insufficient permissions to create subscriptions', 'error')
        return redirect(url_for('notifications.notifications'))
    
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['notification_url', 'resource_type', 'expiration_minutes']
        for field in required_fields:
            if not data.get(field):
                return jsonify({
                    'success': False,
                    'message': f'Missing required field: {field}'
                }), 400
        
        resource_type = data['resource_type']
        keywords = data.get('keywords', [])
        
        # Validate permissions for specific resource types
        user_roles = token_data.get('roles', [])
        if resource_type == 'chats/getAllMessages':
            # For chat subscriptions, Chat.Read.All or Chat.ReadWrite.All is REQUIRED
            # ChatMessage.Read.All is NOT sufficient for creating subscriptions
            if not any(role in user_roles for role in ['Chat.Read.All', 'Chat.ReadWrite.All']):
                return jsonify({
                    'success': False,
                    'message': 'Chat subscriptions require Chat.Read.All or Chat.ReadWrite.All. ChatMessage.Read.All is not sufficient. Add the permission in Azure AD and grant admin consent.'
                }), 403
        
        # Check for existing subscriptions with the same resource
        notifications_api = GraphNotifications(session['graph_token'])
        existing_subs = notifications_api.list_subscriptions()
        
        if existing_subs['success']:
            for sub in existing_subs.get('data', []):
                existing_resource = sub.get('resource', '')
                existing_base = existing_resource.split('?')[0]
                new_base = f"/{resource_type}"
                
                if existing_base == new_base:
                    return jsonify({
                        'success': False,
                        'message': f'A subscription for "{resource_type}" already exists. Only ONE subscription per resource type is allowed. To monitor multiple keywords, delete the existing subscription and create a new one with all keywords combined.'
                    }), 400
        
        # Generate client state if not provided
        client_state = data.get('client_state', str(uuid.uuid4()))
        
        # Calculate expiration datetime
        expiration_minutes = int(data['expiration_minutes'])
        expiration_datetime = datetime.utcnow() + timedelta(minutes=expiration_minutes)
        # Microsoft Graph API requires specific ISO format with 7 decimal places
        expiration_iso = expiration_datetime.strftime('%Y-%m-%dT%H:%M:%S.%fZ')
        
        # Create subscription with optional keywords
        result = notifications_api.create_subscription(
            notification_url=data['notification_url'],
            resource=data['resource_type'],
            expiration_datetime=expiration_iso,
            client_state=client_state,
            keywords=keywords
        )
        
        if result['success']:
            flash('Subscription created successfully', 'success')
            return jsonify(result)
        else:
            return jsonify(result), 400
            
    except Exception as e:
        current_app.logger.error(f"Error creating subscription: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Error creating subscription: {str(e)}'
        }), 500


@notifications_bp.route('/notifications/delete-subscription/<subscription_id>', methods=['DELETE'])
def delete_subscription(subscription_id):
    """Delete a Graph API subscription."""
    user_context = get_user_context()
    token_data = user_context.get('token_data', {})
    if not token_data:
        return redirect(url_for('auth.login'))
    
    access = user_context.get('access', {})
    
    if not access.get('graph_notifications', {}).get('base', False):
        return jsonify({
            'success': False,
            'message': 'Insufficient permissions to delete subscriptions'
        }), 403
    
    try:
        notifications_api = GraphNotifications(session['graph_token'])
        result = notifications_api.delete_subscription(subscription_id)
        
        if result['success']:
            all_notifications = load_notifications()
            all_messages = load_messages()
            
            all_notifications = [
                notif for notif in all_notifications 
                if notif.get('subscription_id') != subscription_id
            ]
            
            all_messages = [
                msg for msg in all_messages 
                if msg.get('subscription_id') != subscription_id
            ]
            
            save_notifications(all_notifications)
            save_messages(all_messages)
            
            flash('Subscription deleted successfully', 'success')
            return jsonify(result)
        else:
            return jsonify(result), 400
            
    except Exception as e:
        current_app.logger.error(f"Error deleting subscription: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Error deleting subscription: {str(e)}'
        }), 500


@notifications_bp.route('/notifications/renew-subscription/<subscription_id>', methods=['POST'])
def renew_subscription(subscription_id):
    """Renew a Graph API subscription."""
    user_context = get_user_context()
    token_data = user_context.get('token_data', {})
    if not token_data:
        return redirect(url_for('auth.login'))
    
    access = user_context.get('access', {})
    
    if not access.get('graph_notifications', {}).get('base', False):
        return jsonify({
            'success': False,
            'message': 'Insufficient permissions to renew subscriptions'
        }), 403
    
    try:
        data = request.get_json() or {}
        expiration_minutes = data.get('expiration_minutes', 1300)
        
        notifications_api = GraphNotifications(session['graph_token'])
        result = notifications_api.renew_subscription(subscription_id, expiration_minutes)
        
        if result['success']:
            flash('Subscription renewed successfully', 'success')
            return jsonify(result)
        else:
            return jsonify(result), 400
            
    except Exception as e:
        current_app.logger.error(f"Error renewing subscription: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Error renewing subscription: {str(e)}'
        }), 500


@notifications_bp.route('/notifications/check-permissions')
def check_permissions():
    """Check available permissions for Graph API Notifications."""
    user_context = get_user_context()
    token_data = user_context.get('token_data', {})
    if not token_data:
        return redirect(url_for('auth.login'))
    
    access = user_context.get('access', {})
    
    # Check specific permissions for different notification types
    available_resources = []
    
    user_roles = token_data.get('roles', [])
    
    # Teams messages - Valid Graph API resource
    if access.get('teams', {}).get('features', {}).get('read_channel_messages', False):
        available_resources.append({
            'type': 'teams/getAllMessages',
            'name': 'Teams Messages',
            'description': 'Monitor Teams messages with keyword filtering. Define specific keywords to track sensitive information like passwords, secrets, or credentials in real-time across all Teams channels. Notifications are triggered when messages contain the specified keywords.',
            'permissions': ['ChannelMessage.Read.All', 'ChannelMessage.ReadWrite.All'],
            'supports_keywords': True,
            'default_keywords': ['secret', 'password', 'senha', 'token', 'credential', 'apikey', 'key', 'pass', 'auth', 'login']
        })
    
    # Teams chat messages - Valid Graph API resource
    if any(role in user_roles for role in ['ChatMessage.Read.All','ChatMessage.ReadWrite.All','Chat.Read.All', 'Chat.ReadWrite.All']):
        available_resources.append({
            'type': 'chats/getAllMessages',
            'name': 'Teams 1:1 and Group Chat Messages',
            'description': 'Monitor all private chat messages across Teams. Track conversations between users in 1:1 and group chats to detect sensitive information sharing or policy violations.',
            'permissions': ['ChatMessage.Read.All','ChatMessage.ReadWrite.All','Chat.Read.All', 'Chat.ReadWrite.All'],
            'supports_keywords': True,
            'default_keywords': ['secret', 'password', 'senha', 'token', 'credential', 'apikey', 'key', 'pass', 'auth', 'login']
        })
    
    # Meeting recordings - Valid Graph API resource
    if any(role in user_roles for role in ['CallRecords.Read.All', 'CallRecords.ReadWrite.All']):
        available_resources.append({
            'type': 'communications/onlineMeetings/getAllRecordings',
            'name': 'Meeting Recordings',
            'description': 'Monitor meeting recordings',
            'permissions': ['CallRecords.Read.All', 'CallRecords.ReadWrite.All']
        })
    
    # Copilot interactions - Valid Graph API resource
    if any(role in user_roles for role in ['AiEnterpriseInteraction.Read.All']):
        available_resources.append({
            'type': 'copilot/interactionHistory/getAllEnterpriseInteractions',
            'name': 'Tenant-wide Copilot Interactions',
            'description': 'Monitor Copilot AI interactions across the organization. Track all enterprise Copilot interactions for security and compliance.',
            'permissions': ['AiEnterpriseInteraction.Read.All']
        })
    
    return jsonify({
        'success': True,
        'available_resources': available_resources
    })


@notifications_bp.route('/api/webhook', methods=['POST', 'GET'])
def webhook_handler():
    """Handle incoming Graph API notifications and validation."""
    try:
        # Check for validation token (first call from Microsoft Graph)
        validation_token = request.args.get('validationToken')
        if validation_token:
            return validation_token, 200
        
        # Process notification
        notification_data = request.get_json()
        if not notification_data:
            return '', 400
        
        notifications_list = notification_data.get('value', [])
        
        # Load existing notifications
        all_notifications = load_notifications()
        all_messages = load_messages()
        
        for notification in notifications_list:
            client_state = notification.get('clientState')
            resource = notification.get('resource')
            subscription_id = notification.get('subscriptionId', 'unknown')
            
            # Create a unique ID to prevent duplicates
            notification_id = notification.get('id') or f"{subscription_id}_{resource}_{notification.get('changeType', 'unknown')}"
            
            notification_info = {
                'id': notification_id,
                'timestamp': datetime.utcnow().isoformat(),
                'resource': resource,
                'client_state': client_state,
                'change_type': notification.get('changeType', 'unknown'),
                'subscription_id': subscription_id,
                'tenant_id': notification.get('tenantId', 'unknown')
            }
            
            # Check if this notification already exists
            if not any(n.get('id') == notification_id for n in all_notifications):
                all_notifications.append(notification_info)
                
                # If it's a Teams message or Chat message, fetch content automatically
                if resource and ('teams(' in resource or 'chats(' in resource):
                    try:
                        message_info = {
                            'notification_id': notification_id,
                            'resource': resource,
                            'timestamp': datetime.utcnow().isoformat(),
                            'subscription_id': subscription_id,
                            'status': 'pending',
                            'message_data': None
                        }
                        
                        if not any(m.get('notification_id') == notification_id for m in all_messages):
                            all_messages.append(message_info)
                    except Exception as e:
                        current_app.logger.error(f"Error preparing message info: {str(e)}")
        
        # Keep only last 100 notifications and messages
        all_notifications = all_notifications[-100:]
        all_messages = all_messages[-100:]
        
        # Save to files
        save_notifications(all_notifications)
        save_messages(all_messages)
        
        return '', 200
        
    except Exception as e:
        current_app.logger.error(f"Error processing webhook: {str(e)}")
        return '', 500


@notifications_bp.route('/api/lifecycle', methods=['POST', 'GET'])
def lifecycle_handler():
    """Handle Microsoft Graph lifecycle notifications."""
    try:
        # Check for validation token
        validation_token = request.args.get('validationToken')
        if validation_token:
            return validation_token, 200
        
        # Process lifecycle notification
        lifecycle_data = request.get_json()
        
        return '', 200
        
    except Exception as e:
        current_app.logger.error(f"Error processing lifecycle webhook: {str(e)}")
        return '', 500


@notifications_bp.route('/api/subscriptions')
def get_subscriptions():
    """Get active subscriptions from Microsoft Graph API."""
    try:
        if 'graph_token' not in session:
            return jsonify({
                'success': False,
                'message': 'No Graph API token available. Please login first.'
            }), 401
        
        # Get subscriptions directly from Microsoft Graph API
        notifications_api = GraphNotifications(session['graph_token'])
        result = notifications_api.list_subscriptions()
        
        if result['success']:
            return jsonify(result)
        else:
            return jsonify(result), 500
        
    except Exception as e:
        current_app.logger.error(f"Error getting subscriptions: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Error getting subscriptions: {str(e)}'
        }), 500


@notifications_bp.route('/api/notifications/latest')
def get_latest_notifications():
    """Get latest notifications from file."""
    try:
        notifications_list = load_notifications()
        
        # Add metadata for notifications that don't have it yet
        if 'graph_token' in session:
            notifications_api = GraphNotifications(session['graph_token'])
            updated = False
            
            for notif in notifications_list:
                # Add metadata if not present
                if not notif.get('title') and notif.get('resource'):
                    try:
                        metadata = notifications_api.get_resource_metadata(notif['resource'])
                        notif['type'] = metadata['type']
                        notif['title'] = metadata['title']
                        notif['subtitle'] = metadata['subtitle']
                        updated = True
                    except Exception as e:
                        current_app.logger.error(f"Error fetching notification metadata: {str(e)}")
            
            # Save updated notifications if any were updated
            if updated:
                save_notifications(notifications_list)
        
        # Return last 10 notifications
        return jsonify({
            'success': True,
            'notifications': notifications_list[-10:] if notifications_list else [],
            'count': len(notifications_list)
        })
        
    except Exception as e:
        current_app.logger.error(f"Error getting latest notifications: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Error getting notifications: {str(e)}'
        }), 500


@notifications_bp.route('/api/messages/latest')
def get_latest_messages():
    """Get latest messages from file and fetch content if needed."""
    try:
        messages = load_messages()
        
        # Fetch content for pending messages if we have a token
        if 'graph_token' in session:
            notifications_api = GraphNotifications(session['graph_token'])
            updated = False
            
            for msg in messages:
                if msg.get('status') == 'pending' and msg.get('resource'):
                    try:
                        # Fetch message content
                        result = notifications_api.get_message_content(msg['resource'])
                        
                        if result['success']:
                            msg['message_data'] = result['data']
                            msg['status'] = 'fetched'
                            
                            # Fetch and save metadata using GraphNotifications
                            metadata = notifications_api.get_resource_metadata(msg['resource'])
                            msg['type'] = metadata['type']
                            msg['title'] = metadata['title']
                            msg['subtitle'] = metadata['subtitle']
                            
                            updated = True
                    except Exception as e:
                        current_app.logger.error(f"Error fetching message content: {str(e)}")
                        msg['status'] = 'error'
                        updated = True
            
            # Save updated messages if any were fetched
            if updated:
                save_messages(messages)
        
        # Return last 10 messages
        return jsonify({
            'success': True,
            'messages': messages[-10:] if messages else [],
            'count': len(messages)
        })
        
    except Exception as e:
        current_app.logger.error(f"Error getting latest messages: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Error getting messages: {str(e)}'
        }), 500


@notifications_bp.route('/api/message-content', methods=['POST'])
def get_message_content():
    """Get message content from Teams resource path."""
    try:
        if 'graph_token' not in session:
            return jsonify({
                'success': False,
                'message': 'No Graph API token available.'
            }), 401
        
        data = request.get_json()
        resource_path = data.get('resource_path')
        
        if not resource_path:
            return jsonify({
                'success': False,
                'message': 'Resource path is required'
            }), 400
        
        notifications_api = GraphNotifications(session['graph_token'])
        result = notifications_api.get_message_content(resource_path)
        
        return jsonify(result)
        
    except Exception as e:
        current_app.logger.error(f"Error getting message content: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Error getting message content: {str(e)}'
        }), 500


def get_chat_message_context(graph_api, chat_id, target_message_id, parent_message_id=None, before=10, after=10):
    """
    Get context messages from a chat (1:1 or group).
    
    Args:
        graph_api: GraphAPI instance
        chat_id: Chat ID
        target_message_id: The target message ID to get context for
        parent_message_id: If the target is a reply, the parent message ID
        before: Number of messages before the target (default: 10)
        after: Number of messages after the target (default: 10)
        
    Returns:
        Dict with before_messages, target_message, after_messages, and metadata
    """
    try:
        if parent_message_id:
            replies_response = graph_api.get(f'/chats/{chat_id}/messages/{parent_message_id}/replies')
            replies = replies_response.get('value', []) if replies_response else []
            
            if not replies:
                return {
                    'success': False,
                    'message': 'No replies found in chat'
                }
            
            replies_sorted = sort_messages_chronologically(replies)
            
            target_index = None
            target_message = None
            
            for idx, msg in enumerate(replies_sorted):
                if msg.get('id') == target_message_id:
                    target_index = idx
                    target_message = msg
                    break
            
            if target_index is None:
                return {
                    'success': False,
                    'message': f'Reply {target_message_id} not found in chat'
                }
            
            before_start = max(0, target_index - before)
            before_messages = replies_sorted[before_start:target_index]
            
            after_end = min(len(replies_sorted), target_index + after + 1)
            after_messages = replies_sorted[target_index + 1:after_end]
            
            parent_message = None
            if before_start == 0:
                parent_response = graph_api.get(f'/chats/{chat_id}/messages/{parent_message_id}')
                if parent_response:
                    parent_message = process_message(parent_response)
            
            before_messages = [process_message(msg) for msg in before_messages]
            target_message = process_message(target_message)
            after_messages = [process_message(msg) for msg in after_messages]
            
            result = {
                'success': True,
                'is_thread': True,
                'parent_message_id': parent_message_id,
                'before_messages': before_messages,
                'target_message': target_message,
                'after_messages': after_messages,
                'total_before': len(before_messages),
                'total_after': len(after_messages),
                'target_index': target_index,
                'total_messages': len(replies_sorted)
            }
            
            if parent_message:
                result['parent_message'] = parent_message
            
            return result
        
        all_messages_response = graph_api.get(f'/chats/{chat_id}/messages')
        all_messages = all_messages_response.get('value', []) if all_messages_response else []
        
        if not all_messages:
            return {
                'success': False,
                'message': 'No messages found in chat'
            }
        
        root_messages = [msg for msg in all_messages if not msg.get('replyToId')]
        root_messages_sorted = sort_messages_chronologically(root_messages)
        target_index = None
        target_message = None
        
        for idx, msg in enumerate(root_messages_sorted):
            if msg.get('id') == target_message_id:
                target_index = idx
                target_message = msg
                break
        
        if target_index is None:
            return {
                'success': False,
                'message': f'Message {target_message_id} not found in chat'
            }
        
        before_start = max(0, target_index - before)
        before_messages = root_messages_sorted[before_start:target_index]
        
        after_end = min(len(root_messages_sorted), target_index + after + 1)
        after_messages = root_messages_sorted[target_index + 1:after_end]
        for msg in before_messages + [target_message] + after_messages:
            msg_id = msg.get('id')
            if msg_id:
                replies_response = graph_api.get(f'/chats/{chat_id}/messages/{msg_id}/replies')
                replies = replies_response.get('value', []) if replies_response else []
                if replies:
                    replies_sorted = sort_messages_chronologically(replies)
                    msg['replies'] = [process_message(reply) for reply in replies_sorted]
        
        before_messages = [process_message(msg) for msg in before_messages]
        target_message = process_message(target_message)
        after_messages = [process_message(msg) for msg in after_messages]
        
        return {
            'success': True,
            'is_thread': False,
            'before_messages': before_messages,
            'target_message': target_message,
            'after_messages': after_messages,
            'total_before': len(before_messages),
            'total_after': len(after_messages),
            'target_index': target_index,
            'total_messages': len(root_messages_sorted)
        }
        
    except Exception as e:
        return {
            'success': False,
            'message': f'Error getting chat message context: {str(e)}'
        }


@notifications_bp.route('/api/message-context', methods=['POST'])
def get_message_context_route():
    """Get message context (before and after messages) from Teams or Chats."""
    try:
        if 'graph_token' not in session:
            return jsonify({
                'success': False,
                'message': 'No Graph API token available.'
            }), 401
        
        data = request.get_json()
        resource_path = data.get('resource_path')
        
        if not resource_path:
            return jsonify({
                'success': False,
                'message': 'Resource path is required'
            }), 400
        
        import re
        from app.utils.graph_api import GraphAPI
        
        teams_reply_match = re.search(r"teams\('([^']+)'\)/channels\('([^']+)'\)/messages\('([^']+)'\)/replies\('([^']+)'\)", resource_path)
        teams_message_match = re.search(r"teams\('([^']+)'\)/channels\('([^']+)'\)/messages\('([^']+)'\)(?!/replies)", resource_path)
        chat_reply_match = re.search(r"chats\('([^']+)'\)/messages\('([^']+)'\)/replies\('([^']+)'\)", resource_path)
        chat_message_match = re.search(r"chats\('([^']+)'\)/messages\('([^']+)'\)(?!/replies)", resource_path)
        
        before_count = data.get('before', 10)
        after_count = data.get('after', 10)
        
        graph_api = GraphAPI(session['graph_token'])
        
        if teams_reply_match or teams_message_match:
            from app.modules.office365.teams.teams import Teams
            teams_module = Teams(graph_api)
            
            if teams_reply_match:
                team_id = teams_reply_match.group(1)
                channel_id = teams_reply_match.group(2)
                parent_message_id = teams_reply_match.group(3)
                message_id = teams_reply_match.group(4)
            else:
                team_id = teams_message_match.group(1)
                channel_id = teams_message_match.group(2)
                message_id = teams_message_match.group(3)
                parent_message_id = None
            
            result = teams_module.get_message_context(
                team_id, 
                channel_id, 
                message_id, 
                parent_message_id=parent_message_id,
                before=before_count, 
                after=after_count
            )
            
            if result['success']:
                team_data = teams_module.get_team_details(team_id)
                channel_data = teams_module.get_channel_details(team_id, channel_id)
                
                result['team_name'] = team_data.get('displayName', 'Unknown Team')
                result['channel_name'] = channel_data.get('displayName', 'Unknown Channel')
                result['resource_type'] = 'teams'
        
        elif chat_reply_match or chat_message_match:
            if chat_reply_match:
                chat_id = chat_reply_match.group(1)
                parent_message_id = chat_reply_match.group(2)
                message_id = chat_reply_match.group(3)
            else:
                chat_id = chat_message_match.group(1)
                message_id = chat_message_match.group(2)
                parent_message_id = None
            
            result = get_chat_message_context(
                graph_api,
                chat_id,
                message_id,
                parent_message_id=parent_message_id,
                before=before_count,
                after=after_count
            )
            
            if result['success']:
                chat_data = graph_api.get(f'/chats/{chat_id}')
                if chat_data:
                    result['chat_topic'] = chat_data.get('topic') or 'Chat'
                    result['chat_type'] = chat_data.get('chatType', 'unknown')
                    result['resource_type'] = 'chat'
                else:
                    result['chat_topic'] = 'Unknown Chat'
                    result['chat_type'] = 'unknown'
                    result['resource_type'] = 'chat'
        
        else:
            return jsonify({
                'success': False,
                'message': 'Invalid resource path format. Supported formats: Teams channels and Chats'
            }), 400
        
        return jsonify(result)
        
    except Exception as e:
        current_app.logger.error(f"Error getting message context: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Error getting message context: {str(e)}'
        }), 500


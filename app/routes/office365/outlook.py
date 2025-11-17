"""
Outlook routes - Fully migrated from routes_old.py
"""

import json
import os
from datetime import datetime, timedelta
from glob import glob
from io import BytesIO

from flask import (
    Blueprint,
    Response,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)

from app.modules.office365.outlook.mail import Outlook
from app.utils.graph_api import GraphAPI
from app.utils.route_helpers import format_message_dates, get_user_context, prepare_module_permissions

outlook_bp = Blueprint('outlook', __name__)



@outlook_bp.route('/outlook')
def outlook_users():
    """List Outlook users."""
    user_context = get_user_context()
    token_data = user_context.get('token_data', {})
    access = user_context.get('access', {})
    
    if not access.get('outlook', {}).get('base', False):
        flash('You do not have permission to access Outlook.', 'error')
        return redirect(url_for('auth.login'))
    
    module_permissions = {
        'outlook': prepare_module_permissions('outlook', access)
    }
    
    users_cache_path = 'results/outlook_users.json'
    
    users = None
    try:
        if os.path.exists(users_cache_path) and 'refresh' not in request.args:
            file_time = os.path.getmtime(users_cache_path)
            file_age = datetime.now() - datetime.fromtimestamp(file_time)
            
            if file_age < timedelta(hours=24):
                with open(users_cache_path, 'r') as f:
                    users = json.load(f)
    except Exception as e:
        current_app.logger.error(f"Error reading users cache file: {str(e)}")
    
    if not users:
        graph_api = GraphAPI(session['graph_token'])
        outlook_module = Outlook(graph_api)
        users = outlook_module.list_users_with_mailboxes()
        
        if users:
            try:
                os.makedirs(os.path.dirname(users_cache_path), exist_ok=True)
                with open(users_cache_path, 'w') as f:
                    json.dump(users, f, indent=2)
            except Exception as e:
                current_app.logger.error(f"Error saving users cache file: {str(e)}")
    
    cache_time = None
    if os.path.exists(users_cache_path):
        cache_time = datetime.fromtimestamp(os.path.getmtime(users_cache_path)).strftime('%Y-%m-%d %H:%M:%S')
    
    return render_template('outlook/users.html',
        users=users,
        access=access,
        module_permissions=module_permissions,
        cache_time=cache_time
    )


@outlook_bp.route('/outlook/refresh')
def refresh_outlook_users():
    """Refresh Outlook users from API."""
    user_context = get_user_context()
    token_data = user_context.get('token_data', {})
    if not token_data:
        return redirect(url_for('auth.login'))
    
    permissions = user_context.get('permissions')
    if not permissions or not permissions.has_base_access('outlook'):
        flash('You do not have permission to refresh Outlook users.', 'error')
        return redirect(url_for('auth.login'))
    
    users_cache_path = 'results/outlook_users.json'
    
    graph_api = GraphAPI(session['graph_token'])
    outlook_module = Outlook(graph_api)
    users = outlook_module.list_users_with_mailboxes()
    
    if users:
        try:
            os.makedirs(os.path.dirname(users_cache_path), exist_ok=True)
            with open(users_cache_path, 'w') as f:
                json.dump(users, f, indent=2)
            flash(f"Successfully refreshed and cached {len(users)} users with mailboxes.", "success")
        except Exception as e:
            flash(f"Error saving cache file: {str(e)}", "error")
    else:
        flash("Failed to fetch users from API.", "error")
    
    return redirect(url_for('outlook.outlook_users'))


@outlook_bp.route('/outlook/mailbox/<user_id>')
@outlook_bp.route('/outlook/mailbox/<user_id>/<folder>')
def view_mailbox(user_id, folder='inbox'):
    """View user mailbox."""
    user_context = get_user_context()
    token_data = user_context.get('token_data', {})
    if not token_data:
        return redirect(url_for('auth.login'))
    
    access = user_context.get('access', {})
    
    if not access.get('outlook', {}).get('base', False):
        flash('You do not have permission to access Outlook.', 'error')
        return redirect(url_for('auth.login'))
    
    module_permissions = {
        'outlook': prepare_module_permissions('outlook', access)
    }
    
    page = int(request.args.get('page', 1))
    
    messages_cache_pattern = f'results/outlook_messages_{user_id}_{folder}_p*.json'
    matching_files = sorted(glob(messages_cache_pattern), reverse=True)
    
    messages = None
    cache_time = None
    
    if matching_files and 'refresh' not in request.args:
        latest_cache = matching_files[0]
        try:
            file_time = os.path.getmtime(latest_cache)
            file_age = datetime.now() - datetime.fromtimestamp(file_time)
            
            if file_age < timedelta(hours=24):
                with open(latest_cache, 'r') as f:
                    messages = json.load(f)
                cache_time = datetime.fromtimestamp(file_time).strftime('%Y-%m-%d %H:%M:%S')
        except Exception as e:
            current_app.logger.error(f"Error reading messages cache: {str(e)}")
    
    if not messages:
        graph_api = GraphAPI(session['graph_token'])
        outlook_module = Outlook(graph_api)
        # Convert page to skip/limit (page 1 = skip 0, page 2 = skip 25, etc.)
        limit = 25
        skip = (page - 1) * limit
        messages = outlook_module.list_messages(user_id, folder, limit=limit, skip=skip)
        
        if messages:
            try:
                messages_cache_path = f'results/outlook_messages_{user_id}_{folder}_p{page}.json'
                os.makedirs(os.path.dirname(messages_cache_path), exist_ok=True)
                with open(messages_cache_path, 'w') as f:
                    json.dump(messages, f, indent=2)
                cache_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            except Exception as e:
                current_app.logger.error(f"Error saving messages cache: {str(e)}")
    
    # Ensure messages is a list
    if not messages:
        messages = []
    
    # Format dates for all messages
    for message in messages:
        format_message_dates(message)
    
    # Get user information
    graph_api = GraphAPI(session['graph_token'])
    user_response = graph_api.get(f'/users/{user_id}?$select=id,displayName,mail,userPrincipalName')
    user_info = user_response if user_response else {
        'id': user_id,
        'displayName': 'Unknown User',
        'mail': '',
        'userPrincipalName': ''
    }
    
    return render_template('outlook/messages.html',
        user_id=user_id,
        user_info=user_info,
        folder=folder,
        messages=messages,
        page=page,
        access=access,
        module_permissions=module_permissions,
        cache_time=cache_time
    )


@outlook_bp.route('/outlook/mailbox/<user_id>/refresh/<folder>')
def refresh_mailbox(user_id, folder='inbox'):
    """Refresh mailbox messages from API."""
    user_context = get_user_context()
    token_data = user_context.get('token_data', {})
    if not token_data:
        return redirect(url_for('auth.login'))
    
    permissions = user_context.get('permissions')
    if not permissions or not permissions.has_base_access('outlook'):
        flash('You do not have permission to refresh Outlook messages.', 'error')
        return redirect(url_for('auth.login'))
    
    page = int(request.args.get('page', 1))
    
    graph_api = GraphAPI(session['graph_token'])
    outlook_module = Outlook(graph_api)
    messages = outlook_module.list_messages(user_id, folder, page=page)
    
    if messages:
        try:
            messages_cache_path = f'results/outlook_messages_{user_id}_{folder}_p{page}.json'
            os.makedirs(os.path.dirname(messages_cache_path), exist_ok=True)
            with open(messages_cache_path, 'w') as f:
                json.dump(messages, f, indent=2)
            flash(f"Successfully refreshed and cached {len(messages)} messages.", "success")
        except Exception as e:
            flash(f"Error saving cache file: {str(e)}", "error")
    else:
        flash("Failed to fetch messages from API.", "error")
    
    return redirect(url_for('outlook.view_mailbox', user_id=user_id, folder=folder, page=page))


@outlook_bp.route('/outlook/mailbox/<user_id>/message/<message_id>')
def view_message(user_id, message_id):
    """View specific message."""
    user_context = get_user_context()
    token_data = user_context.get('token_data', {})
    if not token_data:
        return redirect(url_for('auth.login'))
    
    access = user_context.get('access', {})
    
    if not access.get('outlook', {}).get('base', False):
        flash('You do not have permission to access Outlook.', 'error')
        return redirect(url_for('auth.login'))
    
    module_permissions = {
        'outlook': prepare_module_permissions('outlook', access)
    }
    
    graph_api = GraphAPI(session['graph_token'])
    outlook_module = Outlook(graph_api)
    message = outlook_module.get_message(user_id, message_id)
    
    if not message:
        flash("Message not found.", "error")
        return redirect(url_for('outlook.view_mailbox', user_id=user_id))
    
    format_message_dates(message)
    
    return render_template('outlook/message_detail.html',
        user_id=user_id,
        message=message,
        access=access,
        module_permissions=module_permissions
    )


@outlook_bp.route('/outlook/compose')
@outlook_bp.route('/outlook/compose/<user_id>')
def compose_email(user_id=None):
    """Compose new email."""
    user_context = get_user_context()
    token_data = user_context.get('token_data', {})
    if not token_data:
        return redirect(url_for('auth.login'))
    
    access = user_context.get('access', {})
    
    if not access.get('outlook', {}).get('features', {}).get('send_email', False):
        flash('You do not have permission to send emails.', 'error')
        return redirect(url_for('auth.login'))
    
    module_permissions = {
        'outlook': prepare_module_permissions('outlook', access)
    }
    
    return render_template('outlook/compose.html',
        user_id=user_id,
        access=access,
        module_permissions=module_permissions
    )


@outlook_bp.route('/outlook/reply/<user_id>/<message_id>')
def reply_email(user_id, message_id):
    """Reply to email."""
    user_context = get_user_context()
    token_data = user_context.get('token_data', {})
    if not token_data:
        return redirect(url_for('auth.login'))
    
    access = user_context.get('access', {})
    
    if not access.get('outlook', {}).get('features', {}).get('send_email', False):
        flash('You do not have permission to send emails.', 'error')
        return redirect(url_for('auth.login'))
    
    module_permissions = {
        'outlook': prepare_module_permissions('outlook', access)
    }
    
    graph_api = GraphAPI(session['graph_token'])
    outlook_module = Outlook(graph_api)
    message = outlook_module.get_message(user_id, message_id)
    
    if not message:
        flash("Message not found.", "error")
        return redirect(url_for('outlook.view_mailbox', user_id=user_id))
    
    format_message_dates(message)
    
    reply_to = message.get('from', {}).get('emailAddress', {}).get('address', '')
    reply_subject = message.get('subject', '')
    if not reply_subject.startswith('Re:'):
        reply_subject = f"Re: {reply_subject}"
    
    return render_template('outlook/compose.html',
        user_id=user_id,
        reply_to=reply_to,
        reply_subject=reply_subject,
        original_message=message,
        access=access,
        module_permissions=module_permissions
    )


@outlook_bp.route('/outlook/send', methods=['POST'])
def send_email():
    """Send email."""
    user_context = get_user_context()
    token_data = user_context.get('token_data', {})
    if not token_data:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    
    permissions = user_context.get('permissions')
    if not permissions or not permissions.has_feature_access('outlook', 'send_email'):
        return jsonify({'success': False, 'message': 'Insufficient permissions to send emails'}), 403
    
    try:
        data = request.get_json()
        user_id = data.get('user_id')
        # Accept both 'to' and 'to_recipients' for compatibility
        to_raw = data.get('to') or data.get('to_recipients', '')
        subject = data.get('subject', '')
        body = data.get('body', '')
        
        # Parse and clean recipients
        to_recipients = [r.strip() for r in to_raw.split(',') if r.strip()]
        
        # Validate required fields
        if not user_id:
            return jsonify({'success': False, 'message': 'user_id is required'}), 400
        if not to_recipients:
            return jsonify({'success': False, 'message': 'At least one recipient is required'}), 400
        if not subject:
            return jsonify({'success': False, 'message': 'Subject is required'}), 400
        
        graph_api = GraphAPI(session['graph_token'])
        outlook_module = Outlook(graph_api)
        
        # Call send_email with correct parameters
        result = outlook_module.send_email(
            subject=subject,
            body=body,
            to_recipients=to_recipients,
            user_id=user_id
        )
        
        # send_email returns a dict with 'success' and 'message' keys
        return jsonify(result)
            
    except Exception as e:
        current_app.logger.error(f"Error sending email: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500


@outlook_bp.route('/outlook/attachment/<user_id>/<message_id>/<attachment_id>')
def download_attachment(user_id, message_id, attachment_id):
    """Download email attachment."""
    user_context = get_user_context()
    token_data = user_context.get('token_data', {})
    if not token_data:
        return redirect(url_for('auth.login'))
    
    permissions = user_context.get('permissions')
    if not permissions or not permissions.has_base_access('outlook'):
        flash('You do not have permission to download attachments.', 'error')
        return redirect(url_for('auth.login'))
    
    try:
        graph_api = GraphAPI(session['graph_token'])
        outlook_module = Outlook(graph_api)
        
        attachment = outlook_module.get_attachment(user_id, message_id, attachment_id)
        
        if not attachment:
            flash("Attachment not found.", "error")
            return redirect(url_for('outlook.view_message', user_id=user_id, message_id=message_id))
        
        content_bytes = attachment.get('contentBytes', '')
        if content_bytes:
            import base64
            file_data = base64.b64decode(content_bytes)
            
            filename = attachment.get('name', 'attachment')
            content_type = attachment.get('contentType', 'application/octet-stream')
            
            return send_file(
                BytesIO(file_data),
                mimetype=content_type,
                as_attachment=True,
                download_name=filename
            )
        else:
            flash("Attachment content not available.", "error")
            return redirect(url_for('outlook.view_message', user_id=user_id, message_id=message_id))
            
    except Exception as e:
        current_app.logger.error(f"Error downloading attachment: {str(e)}")
        flash(f"Error downloading attachment: {str(e)}", "error")
        return redirect(url_for('outlook.view_message', user_id=user_id, message_id=message_id))

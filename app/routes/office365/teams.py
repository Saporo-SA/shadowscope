"""
Microsoft Teams routes.
"""

import json
import os
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

from app.modules.entraID.security_principals import SecurityPrincipals
from app.modules.office365.teams.teams import Teams
from app.utils.graph_api import GraphAPI
from app.utils.route_helpers import (
    handle_api_errors,
    get_user_context,
    require_auth,
    prepare_module_permissions,
)

teams_bp = Blueprint('teams', __name__)



@teams_bp.route('/teams')
@require_auth
@handle_api_errors
def list_teams():
    """List all Microsoft Teams."""
    user_context = get_user_context()
    token_data = user_context.get('token_data', {})
    access = user_context.get('access', {})
    
    if not access.get('teams', {}).get('base', False):
        flash('You do not have permission to access this page.', 'error')
        return redirect(url_for('dashboard.dashboard'))
    
    module_permissions = {
        'teams': prepare_module_permissions('teams', access)
    }
    
    teams_cache_path = 'results/teams.json'
    
    teams = None
    try:
        if os.path.exists(teams_cache_path) and 'refresh' not in request.args:
            file_time = os.path.getmtime(teams_cache_path)
            file_age = datetime.now() - datetime.fromtimestamp(file_time)
            
            if file_age < timedelta(hours=24):
                with open(teams_cache_path, 'r') as f:
                    teams = json.load(f)
    except Exception as e:
        current_app.logger.error(f"Error reading teams cache file: {str(e)}")
    
    if not teams:
        graph_api = GraphAPI(session['graph_token'])
        teams_module = Teams(graph_api)
        teams = teams_module.list_teams()
        
        if teams:
            try:
                os.makedirs(os.path.dirname(teams_cache_path), exist_ok=True)
                with open(teams_cache_path, 'w') as f:
                    json.dump(teams, f, indent=2)
            except Exception as e:
                current_app.logger.error(f"Error saving teams cache file: {str(e)}")
    
    cache_time = None
    if os.path.exists(teams_cache_path):
        cache_time = datetime.fromtimestamp(os.path.getmtime(teams_cache_path)).strftime('%Y-%m-%d %H:%M:%S')
    
    return render_template('teams/teams.html', teams=teams, access=access, module_permissions=module_permissions, cache_time=cache_time)


@teams_bp.route('/teams/refresh')
def refresh_teams():
    """Refresh teams data from API."""
    user_context = get_user_context()
    token_data = user_context.get('token_data', {})
    if not token_data:
        return redirect(url_for('auth.login'))
    
    permissions = user_context.get('permissions')
    if not permissions or not permissions.has_base_access('teams'):
        flash('You do not have permission to refresh teams data.', 'error')
        return redirect(url_for('dashboard.dashboard'))
    
    teams_cache_path = 'results/teams.json'
    
    graph_api = GraphAPI(session['graph_token'])
    teams_module = Teams(graph_api)
    teams = teams_module.list_teams()
    
    if teams:
        try:
            os.makedirs(os.path.dirname(teams_cache_path), exist_ok=True)
            with open(teams_cache_path, 'w') as f:
                json.dump(teams, f, indent=2)
            flash(f"Successfully refreshed and cached {len(teams)} teams.", "success")
        except Exception as e:
            flash(f"Error saving cache file: {str(e)}", "error")
    else:
        flash("Failed to fetch teams from API.", "error")
    
    return redirect(url_for('teams.list_teams'))


@teams_bp.route('/teams/<team_id>/members')
def edit_team_members(team_id):
    """Edit team members."""
    try:
        user_context = get_user_context()
        token_data = user_context.get('token_data', {})
        access = user_context.get('access', {})
        
        permissions = user_context.get('permissions')
        if not permissions or not permissions.has_base_access('teams'):
            return redirect(url_for('teams.list_teams'))
        
        graph = GraphAPI(session['graph_token'])
        teams_module = Teams(graph)
        
        team = teams_module.get_team_details(team_id)
        if not team:
            return "Team not found", 404
            
        members = teams_module.list_team_members(team_id) or []
        users = SecurityPrincipals(graph, token_data.get('roles', [])).get_users() or []
        
        return render_template(
            'teams/teams_members.html',
            access=access,
            team=team,
            members=members,
            users=users
        )
        
    except Exception as e:
        current_app.logger.error(f"Error in edit_team_members: {str(e)}")
        return f"Server error: {str(e)}", 500


@teams_bp.route('/teams/<team_id>/add_member', methods=['POST'])
@require_auth
@handle_api_errors
def add_team_member(team_id):
    """Add member to team."""
    if 'graph_token' not in session:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    
    try:
        current_app.logger.info(f"Processing add member request for team {team_id}")
        user_context = get_user_context()
        token_data = user_context.get('token_data', {})
        access = user_context.get('access', {})
        
        if not access.get('teams', {}).get('base', False):
            current_app.logger.warning("Insufficient permissions")
            return jsonify({'success': False, 'message': 'Insufficient permissions'}), 403
        
        data = request.get_json()
        member_id = data.get('member_id')
        
        if not member_id:
            current_app.logger.warning("No member_id provided")
            return jsonify({'success': False, 'message': 'Member ID is required'}), 400
        
        graph = GraphAPI(session['graph_token'])
        teams_module = Teams(graph)
        
        current_app.logger.info(f"Attempting to add member {member_id} to team {team_id}")
        success = teams_module.add_team_member(team_id, member_id)
        
        if success:
            current_app.logger.info("Member added successfully")
            return jsonify({'success': True, 'message': 'Member added successfully'})
        else:
            current_app.logger.warning("Failed to add member")
            error_message = 'Failed to add member'
            if hasattr(teams_module, 'last_error'):
                error_message = teams_module.last_error
                current_app.logger.error(f"Error details: {error_message}")

                if 'session may have expired' in error_message.lower():
                    return jsonify({
                        'success': False, 
                        'message': 'Session may have expired. Please try logging in again.'
                    }), 401
                    
            return jsonify({'success': False, 'message': error_message}), 500
            
    except Exception as e:
        current_app.logger.error(f"Error in add_team_member: {str(e)}")
        if hasattr(e, 'response') and hasattr(e.response, 'text'):
            response_text = e.response.text

            if response_text.strip().startswith('<!doctype') or response_text.strip().startswith('<html'):
                current_app.logger.warning("Received HTML response, likely session expiration")
                return jsonify({
                    'success': False, 
                    'message': 'Session may have expired. Please try logging in again.'
                }), 401

            try:
                error_json = json.loads(response_text)
                if 'error' in error_json:
                    error_message = error_json['error'].get('message', 'Unknown error')
                    current_app.logger.error(f"Extracted error message: {error_message}")
                    return jsonify({'success': False, 'message': error_message}), 500
            except (ValueError, KeyError, TypeError) as parse_error:
                current_app.logger.warning(f"Error parsing error response: {parse_error}")
                pass
        
        return jsonify({'success': False, 'message': str(e)}), 500


@teams_bp.route('/teams/<team_id>/remove_member', methods=['POST'])
@require_auth
@handle_api_errors
def remove_team_member(team_id):
    """Remove member from team."""
    if 'graph_token' not in session:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    
    try:
        user_context = get_user_context()
        token_data = user_context.get('token_data', {})
        access = user_context.get('access', {})
        
        if not access.get('teams', {}).get('base', False):
            return jsonify({'success': False, 'message': 'Insufficient permissions'}), 403
        
        data = request.get_json()
        member_id = data.get('member_id')
        
        if not member_id:
            return jsonify({'success': False, 'message': 'Member ID is required'}), 400
        
        graph = GraphAPI(session['graph_token'])
        teams_module = Teams(graph)
        
        try:
            success = teams_module.remove_team_member(team_id, member_id)
            
            if success:
                return jsonify({'success': True, 'message': 'Member removed successfully'})
            else:
                return jsonify({'success': False, 'message': 'Failed to remove member'}), 500
        except Exception as team_error:
            # Re-raise the specific error from the teams module
            raise team_error
            
    except Exception as e:
        current_app.logger.error(f"Error in remove_team_member: {str(e)}")
        
        # Check if it's a specific API error
        if hasattr(e, 'response') and hasattr(e.response, 'text'):
            try:
                error_data = json.loads(e.response.text)
                error_message = error_data.get('error', {}).get('message', str(e))
                current_app.logger.error(f"API Error: {error_message}")
                return jsonify({'success': False, 'message': error_message}), 500
            except (json.JSONDecodeError, KeyError, AttributeError):
                pass
        
        return jsonify({'success': False, 'message': str(e)}), 500


@teams_bp.route('/teams/<team_id>/channels')
def list_team_channels(team_id):
    """List team channels."""
    user_context = get_user_context()
    token_data = user_context.get('token_data', {})
    access = user_context.get('access', {})
    
    if not access.get('teams', {}).get('base', False):
        flash('You do not have permission to access this page.', 'error')
        return redirect(url_for('dashboard.dashboard'))
    
    module_permissions = {
        'teams': prepare_module_permissions('teams', access)
    }
    
    graph_api = GraphAPI(session['graph_token'])
    teams_module = Teams(graph_api)
    team = teams_module.get_team_details(team_id)
    channels = teams_module.list_team_channels(team_id)
    
    return render_template('teams/channels.html', team=team, channels=channels, access=access, module_permissions=module_permissions)


@teams_bp.route('/teams/<team_id>/channels/<channel_id>/messages')
def list_channel_messages(team_id, channel_id):
    """List channel messages."""
    if 'graph_token' not in session:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.headers.get('Accept') == 'application/json':
            return jsonify({'success': False, 'message': 'Not authenticated'}), 401
        return redirect(url_for('auth.login'))
    
    user_context = get_user_context()
    token_data = user_context.get('token_data', {})
    access = user_context.get('access', {})
    
    has_base_perm = access.get('teams', {}).get('base', False)
    has_message_perm = access.get('teams', {}).get('features', {}).get('read_channel_messages', False)
    
    if not has_base_perm or not has_message_perm:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.headers.get('Accept') == 'application/json':
            return jsonify({
                'success': False, 
                'message': 'Insufficient permissions. Need Team.Read.All and ChannelMessage.Read.All permissions.'
            }), 403
            
        flash('You do not have permission to read channel messages. You need the ChannelMessage.Read.All permission.', 'error')
        return redirect(url_for('teams.list_team_channels', team_id=team_id))
    
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.headers.get('Accept') == 'application/json' or 'page' in request.args
    
    graph_api = GraphAPI(session['graph_token'])
    teams_module = Teams(graph_api)
    
    # Clear cache if refresh is requested
    if 'refresh' in request.args:
        teams_module.clear_message_cache()
    
    if is_ajax:
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 10))
        skip = (page - 1) * limit
        
        messages = teams_module.list_channel_messages(team_id, channel_id, limit=limit, skip=skip)
        
        all_messages = teams_module.get_all_channel_messages(team_id, channel_id)
        root_messages_count = len([msg for msg in all_messages if msg.get('replyToId') is None or msg.get('replyToId') == 'null' or msg.get('replyToId') == '']) if all_messages else 0
        has_more = (skip + len(messages)) < root_messages_count
        
        return jsonify({
            'success': True,
            'messages': messages,
            'has_more': has_more,
            'total': root_messages_count
        })
    else:
        module_permissions = {
            'teams': prepare_module_permissions('teams', access)
        }
        
        team = teams_module.get_team_details(team_id)
        channel = teams_module.get_channel_details(team_id, channel_id)
        
        if not team or not channel:
            flash('Team or channel not found', 'error')
            return redirect(url_for('teams.list_teams'))
        
        messages = teams_module.list_channel_messages(team_id, channel_id, limit=10)
        
        all_messages = teams_module.get_all_channel_messages(team_id, channel_id)
        root_messages_count = len([msg for msg in all_messages if msg.get('replyToId') is None or msg.get('replyToId') == 'null' or msg.get('replyToId') == '']) if all_messages else 0
        has_more = len(messages) < root_messages_count
        
        return render_template('teams/channel_messages.html', 
                             team=team, 
                             channel=channel, 
                             messages=messages,
                             access=access,
                             module_permissions=module_permissions,
                             has_more=has_more,
                             total_messages=root_messages_count)


@teams_bp.route('/teams/<team_id>/channels/<channel_id>/members')
def edit_channel_members(team_id, channel_id):
    """Edit channel members."""
    try:
        user_context = get_user_context()
        token_data = user_context.get('token_data', {})
        access = user_context.get('access', {})
        
        permissions = user_context.get('permissions')
        if not permissions or not permissions.has_base_access('teams'):
            return redirect(url_for('teams.list_teams'))
        
        graph = GraphAPI(session['graph_token'])
        teams_module = Teams(graph)
        
        team = teams_module.get_team_details(team_id)
        if not team:
            return "Team not found", 404
            
        channel = teams_module.get_channel_details(team_id, channel_id)
        if not channel:
            return "Channel not found", 404
            
        team_members = teams_module.list_team_members(team_id)
        
        channel_members = teams_module.list_channel_members(team_id, channel_id)
        channel_member_ids = {m.get('userId') for m in channel_members}
        
        available_users = []
        for member in team_members:
            member_id = member.get('userId')
            if member_id and member_id not in channel_member_ids:
                available_users.append(member)
        
        return render_template(
            'teams/channel_members.html',
            access=access,
            team=team,
            channel=channel,
            members=channel_members,
            users=available_users
        )
        
    except Exception as e:
        current_app.logger.error(f"Error in edit_channel_members: {str(e)}")
        return f"Server error: {str(e)}", 500


@teams_bp.route('/teams/<team_id>/channels/<channel_id>/add_member', methods=['POST'])
def add_channel_member(team_id, channel_id):
    """Add member to channel."""
    if 'graph_token' not in session:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    
    try:
        user_context = get_user_context()
        token_data = user_context.get('token_data', {})
        access = user_context.get('access', {})
        
        if not access.get('teams', {}).get('base', False):
            return jsonify({'success': False, 'message': 'Insufficient permissions'}), 403
        
        data = request.get_json()
        member_id = data.get('member_id')
        
        if not member_id:
            return jsonify({'success': False, 'message': 'Member ID is required'}), 400
        
        graph = GraphAPI(session['graph_token'])
        teams_module = Teams(graph)
        
        success = teams_module.add_channel_member(team_id, channel_id, member_id)
        
        if success:
            return jsonify({'success': True, 'message': 'Member added successfully'})
        else:
            return jsonify({'success': False, 'message': 'Failed to add member'}), 400
            
    except Exception as e:
        current_app.logger.error(f"Error in add_channel_member: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500


@teams_bp.route('/teams/<team_id>/channels/<channel_id>/remove_member', methods=['POST'])
def remove_channel_member(team_id, channel_id):
    """Remove member from channel."""
    if 'graph_token' not in session:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    
    try:
        user_context = get_user_context()
        token_data = user_context.get('token_data', {})
        access = user_context.get('access', {})
        
        if not access.get('teams', {}).get('base', False):
            return jsonify({'success': False, 'message': 'Insufficient permissions'}), 403
        
        data = request.get_json()
        member_id = data.get('member_id')
        
        if not member_id:
            return jsonify({'success': False, 'message': 'Member ID is required'}), 400
        
        graph = GraphAPI(session['graph_token'])
        teams_module = Teams(graph)
        
        try:
            success = teams_module.remove_channel_member(team_id, channel_id, member_id)
            
            if success:
                return jsonify({'success': True, 'message': 'Member removed successfully'})
            else:
                return jsonify({'success': False, 'message': 'Failed to remove member'}), 500
        except Exception as team_error:
            # Re-raise the specific error from the teams module
            raise team_error
            
    except Exception as e:
        current_app.logger.error(f"Error in remove_channel_member: {str(e)}")
        
        # Check if it's a specific API error
        if hasattr(e, 'response') and hasattr(e.response, 'text'):
            try:
                error_data = json.loads(e.response.text)
                error_message = error_data.get('error', {}).get('message', str(e))
                current_app.logger.error(f"API Error: {error_message}")
                return jsonify({'success': False, 'message': error_message}), 500
            except (json.JSONDecodeError, KeyError, AttributeError):
                pass
        
        return jsonify({'success': False, 'message': str(e)}), 500


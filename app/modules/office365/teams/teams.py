from app.utils.graph_api import GraphAPI
from app.utils.message_utils import process_message, sort_messages_chronologically
from typing import List, Dict, Optional, Union
import json
from concurrent.futures import ThreadPoolExecutor, as_completed

class Teams:
    """
    Microsoft Teams management class for interacting with Teams API.
    
    Provides methods to list teams, manage channels, and handle team memberships.
    """
    
    def __init__(self, graph_api: GraphAPI):
        """
        Initialize Teams manager with Graph API client.
        
        Args:
            graph_api (GraphAPI): Authenticated Graph API client instance
        """
        self.graph_api = graph_api

    def list_teams(self):
        """List all teams in the organization"""
        try:
            endpoint = "/teams"
            response = self.graph_api.get(endpoint)
            
            if response is None:
                return []
                
            teams = response.get('value', [])
            return teams
        except Exception as e:
            return []

    def list_team_channels(self, team_id: str):
        """List all channels for a specific team"""
        try:
            endpoint = f"/teams/{team_id}/channels"
            response = self.graph_api.get(endpoint)
            
            if response is None:
                return []
                
            channels = response.get('value', [])
            return channels
        except Exception as e:
            return []

    def get_team_details(self, team_id: str):
        """Get details for a specific team"""
        try:
            endpoint = f"/teams/{team_id}"
            response = self.graph_api.get(endpoint)
            
            if response is None:
                # Return a minimal team object with the ID to prevent errors
                return {"id": team_id, "displayName": "Unknown Team"}
                
            return response
        except Exception as e:
            if hasattr(e, 'response') and hasattr(e.response, 'text'):
                pass  # Error details available but not logging them
            # Return a minimal team object with the ID to prevent errors
            return {"id": team_id, "displayName": "Unknown Team"}

    def list_team_members(self, team_id):
        """List all members of a team"""
        try:
            response = self.graph_api.get(f'/teams/{team_id}/members')
            
            if response is None:
                return []
                
            members = response.get('value', [])
            
            processed_members = []
            for member in members:
                user_bind = member.get('user@odata.bind', '')
                if user_bind:
                    user_id = user_bind.split('/')[-1]
                    member['id'] = user_id
                
                # Add role information
                roles = member.get('roles', [])
                member['is_owner'] = 'owner' in [role.lower() for role in roles]
                member['role_display'] = 'Owner' if member['is_owner'] else 'Member'
                
                processed_members.append(member)
            
            return processed_members
        except Exception as e:
            return []

    def get_channel_details(self, team_id, channel_id):
        """Get details of a specific channel"""
        try:
            response = self.graph_api.get(f'/teams/{team_id}/channels/{channel_id}')
            
            if response is None:
                # Return a minimal channel object with IDs to prevent errors
                return {"id": channel_id, "displayName": "Unknown Channel", "teamId": team_id}
                
            return response
        except Exception as e:
            if hasattr(e, 'response') and hasattr(e.response, 'text'):
                pass  # Error details available but not logging them
            # Return a minimal channel object with IDs to prevent errors
            return {"id": channel_id, "displayName": "Unknown Channel", "teamId": team_id}

    def get_message_replies(self, team_id, channel_id, message_id):
        """Get replies to a specific message with caching"""
        if not hasattr(self, '_replies_cache'):
            self._replies_cache = {}
        
        cache_key = f"{team_id}_{channel_id}_{message_id}"
        
        if cache_key not in self._replies_cache:
            try:
                result = self.graph_api.get(f'/teams/{team_id}/channels/{channel_id}/messages/{message_id}/replies')
                replies = result.get('value', []) if result else []
                self._replies_cache[cache_key] = replies
            except Exception as e:
                self._replies_cache[cache_key] = []
        
        return self._replies_cache[cache_key]
    
    def get_message_context(self, team_id, channel_id, target_message_id, parent_message_id=None, before=10, after=10):
        """
        Get context messages around a specific message (before and after).
        
        Args:
            team_id (str): Team ID
            channel_id (str): Channel ID
            target_message_id (str): The target message ID to get context for
            parent_message_id (str): If the target is a reply, the parent message ID
            before (int): Number of messages before the target (default: 10)
            after (int): Number of messages after the target (default: 10)
            
        Returns:
            Dict with before_messages, target_message, after_messages, and metadata
        """
        try:
            if parent_message_id:
                replies = self.get_message_replies(team_id, channel_id, parent_message_id)
                
                if not replies:
                    return {
                        'success': False,
                        'message': 'No replies found in thread'
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
                        'message': f'Reply {target_message_id} not found in thread'
                    }
                
                before_start = max(0, target_index - before)
                before_messages = replies_sorted[before_start:target_index]
                
                after_end = min(len(replies_sorted), target_index + after + 1)
                after_messages = replies_sorted[target_index + 1:after_end]
                
                parent_message = None
                include_parent = (before_start == 0)
                
                if include_parent:
                    all_messages = self.get_all_channel_messages(team_id, channel_id)
                    for msg in all_messages:
                        if msg.get('id') == parent_message_id:
                            parent_message = process_message(msg)
                            break
                
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
            
            all_messages = self.get_all_channel_messages(team_id, channel_id)
            
            if not all_messages:
                return {
                    'success': False,
                    'message': 'No messages found in channel'
                }
            
            target_message = None
            for msg in all_messages:
                if msg.get('id') == target_message_id:
                    target_message = msg
                    break
            
            if not target_message:
                return {
                    'success': False,
                    'message': f'Message {target_message_id} not found in channel'
                }
            
            replies = self.get_message_replies(team_id, channel_id, target_message_id)
            if not replies:
                target_message = process_message(target_message)
                return {
                    'success': True,
                    'is_thread': False,
                    'before_messages': [],
                    'target_message': target_message,
                    'after_messages': [],
                    'total_before': 0,
                    'total_after': 0,
                    'target_index': 0,
                    'total_messages': 1
                }
            
            replies_sorted = sort_messages_chronologically(replies)
            
            target_message = process_message(target_message)
            target_message['replies'] = [process_message(reply) for reply in replies_sorted]
            
            return {
                'success': True,
                'is_thread': False,
                'is_root_message': True,
                'before_messages': [],
                'target_message': target_message,
                'after_messages': [],
                'total_before': 0,
                'total_after': len(replies_sorted),
                'target_index': 0,
                'total_messages': 1 + len(replies_sorted)
            }
            
        except Exception as e:
            return {
                'success': False,
                'message': f'Error getting message context: {str(e)}'
            }
    
    def clear_message_cache(self):
        """Clear the internal message and replies cache"""
        if hasattr(self, '_message_cache'):
            self._message_cache = {}
        if hasattr(self, '_replies_cache'):
            self._replies_cache = {}
    
    def get_all_channel_messages(self, team_id, channel_id):
        """Get all messages from a channel (cached internally)"""
        if not hasattr(self, '_message_cache'):
            self._message_cache = {}
        
        cache_key = f"{team_id}_{channel_id}"
        
        if cache_key not in self._message_cache:
            try:
                endpoint = f'teams/{team_id}/channels/{channel_id}/messages'
                all_messages = self.graph_api.get_paginated(endpoint)
                self._message_cache[cache_key] = all_messages if all_messages else []
            except Exception as e:
                self._message_cache[cache_key] = []
        
        return self._message_cache[cache_key]
    
    def list_channel_messages(self, team_id, channel_id, limit=10, skip=0, include_replies=True):
        """List messages from a channel with optional replies"""
        try:
            all_messages = self.get_all_channel_messages(team_id, channel_id)
            
            
            if not all_messages:
                return []
            
            # Microsoft Graph API returns 'null' as a string for replyToId on root messages, not None
            root_messages = [msg for msg in all_messages if msg.get('replyToId') is None or msg.get('replyToId') == 'null' or msg.get('replyToId') == '']
            
            start_index = skip
            end_index = skip + limit
            messages = root_messages[start_index:end_index]
            
            # Ensure all messages have required fields
            for message in messages:
                if not isinstance(message, dict):
                    continue
                
                if 'from' not in message or not message['from']:
                    message['from'] = {'user': {'displayName': 'Unknown'}}
                elif 'user' not in message['from'] or not message['from']['user']:
                    message['from']['user'] = {'displayName': 'Unknown'}
                
                if 'body' not in message or not message['body']:
                    message['body'] = {'content': 'No content'}
            
            # Fetch replies in parallel for better performance
            if include_replies and messages:
                def fetch_replies_for_message(message):
                    message_id = message.get('id')
                    if not message_id:
                        return message
                    
                    replies = self.get_message_replies(team_id, channel_id, message_id)
                    
                    if replies:
                        for reply in replies:
                            if not isinstance(reply, dict):
                                continue
                            
                            if 'from' not in reply or not reply['from']:
                                reply['from'] = {'user': {'displayName': 'Unknown'}}
                            elif 'user' not in reply['from'] or not reply['from']['user']:
                                reply['from']['user'] = {'displayName': 'Unknown'}
                            
                            if 'body' not in reply or not reply['body']:
                                reply['body'] = {'content': 'No content'}
                        
                        message['replies'] = replies
                    return message
                
                # Use ThreadPoolExecutor to fetch replies in parallel
                with ThreadPoolExecutor(max_workers=5) as executor:
                    future_to_message = {executor.submit(fetch_replies_for_message, msg): msg for msg in messages}
                    for future in as_completed(future_to_message):
                        pass  # Results are already stored in the message objects
            
            return messages
            
        except Exception as e:
            if hasattr(e, 'response') and hasattr(e.response, 'text'):
                pass
            return []

    def list_channel_members(self, team_id, channel_id):
        """List all members of a channel"""
        try:
            response = self.graph_api.get(f'/teams/{team_id}/channels/{channel_id}/members')
            
            if response is None:
                return []
                
            members = response.get('value', [])
            
            # Process members to extract user IDs from user@odata.bind URLs
            processed_members = []
            for member in members:
                user_bind = member.get('user@odata.bind', '')
                if user_bind:
                    # Extract user ID from the URL (e.g., "https://graph.microsoft.com/v1.0/users/123456")
                    user_id = user_bind.split('/')[-1]
                    member['id'] = user_id
                processed_members.append(member)
            
            return processed_members
        except Exception as e:
            return []

    def add_team_member(self, team_id: str, user_id: str) -> bool:
        """Add a user to a team"""
        
        try:
            endpoint = f'/teams/{team_id}/members'
            data = {
                '@odata.type': '#microsoft.graph.aadUserConversationMember',
                'roles': [],  # Empty roles for regular members
                'user@odata.bind': f'https://graph.microsoft.com/v1.0/users/{user_id}'
            }
            
            response = self.graph_api.post(endpoint, payload=data)
            
            if hasattr(response, 'status_code'):
                success = response.status_code in [200, 201, 204]
                
                if not success and hasattr(response, 'text'):
                    self.last_error = response.text
                    
                    # If it's an HTML response, the session has likely expired
                    if response.text.strip().startswith('<!doctype') or response.text.strip().startswith('<html'):
                        self.last_error = "Session may have expired. Please try logging in again."
                        return False
                    
                    # Try to extract more specific error message
                    try:
                        error_json = json.loads(response.text)
                        if 'error' in error_json:
                            self.last_error = error_json['error'].get('message', 'Unknown error')
                    except (ValueError, KeyError, TypeError):
                        pass
                
                return success
            else:
                self.last_error = "Invalid response from server"
                return False
                
        except Exception as e:
            if hasattr(e, 'response') and hasattr(e.response, 'text'):
                pass  # Error details available but not logging them
                self.last_error = e.response.text
                
                # If it's an HTML response, the session has likely expired
                if e.response.text.strip().startswith('<!doctype') or e.response.text.strip().startswith('<html'):
                    self.last_error = "Session may have expired. Please try logging in again."
            else:
                self.last_error = str(e)
            return False

    def add_channel_member(self, team_id: str, channel_id: str, user_id: str) -> bool:
        try:
            
            # First, try to find the user's actual Azure AD Object ID
            # The user_id you're currently passing appears to be an encoded ID
            # We need to find the actual Azure AD ID (UUID format)
            team_members = self.list_team_members(team_id)
            
            # Try to find the matching user
            azure_user_id = None
            for member in team_members:
                if member.get('id') == user_id:  # If the encoded ID matches
                    azure_user_id = member.get('userId')  # This should be the UUID format
                    break
                    
            if not azure_user_id:
                return False
            
            # Add the user to the channel with the correct UUID format
            endpoint = f'teams/{team_id}/channels/{channel_id}/members'
            
            data = {
                '@odata.type': '#microsoft.graph.aadUserConversationMember',
                'roles': [],
                'user@odata.bind': f'https://graph.microsoft.com/v1.0/users/{azure_user_id}'
            }
            
            response = self.graph_api.post(endpoint, payload=data)
            success = response is not None and (response.status_code == 201 or response.status_code == 200)
            return success
                
        except Exception as e:
            if hasattr(e, 'response') and hasattr(e.response, 'text'):
                pass  # Error details available but not logging them
            return False

    def remove_channel_member(self, team_id: str, channel_id: str, user_id: str) -> bool:
        """
        Remove a user from a channel.
        
        Args:
            team_id (str): ID of the team
            channel_id (str): ID of the channel
            user_id (str): User ID to remove (this could be a Base64 encoded ID or Azure AD ID)
            
        Returns:
            bool: True if the user was removed successfully, False otherwise
        """
        try:
            # Get the channel members
            channel_members = self.list_channel_members(team_id, channel_id)
            
            # Find the member in the channel either by id or userId
            member_id = None
            for member in channel_members:
                # Try to match with either the encoded ID or the Azure AD ID
                if member.get('id') == user_id or member.get('userId') == user_id:
                    member_id = member.get('id')  # We need the encoded ID for deletion
                    break
                    
            if not member_id:
                return False
            
            # Remove the member using the encoded conversation member ID
            endpoint = f'/teams/{team_id}/channels/{channel_id}/members/{member_id}'
            
            response = self.graph_api.delete(endpoint)
            
            # Check if the response is a Response object
            if hasattr(response, 'status_code'):
                success = response.status_code in [200, 201, 204]
                
                return success
            else:
                return False
            
        except Exception as e:
            if hasattr(e, 'response') and hasattr(e.response, 'text'):
                error_text = e.response.text
                
                # Try to parse JSON error first to get the actual error message
                try:
                    import json
                    error_data = json.loads(error_text)
                    error_message = error_data.get('error', {}).get('message', '')
                    error_code = error_data.get('error', {}).get('code', '')
                    
                    # Check for specific error codes/messages from Microsoft Graph API
                    if error_code == 'BadRequest' and ('operation not supported' in error_message.lower() or 'cannot remove' in error_message.lower()):
                        # This might be a channel that doesn't support member removal
                        if 'general' in error_message.lower():
                            raise Exception("Cannot remove members from the General channel. The General channel always includes all team members.")
                        else:
                            # Return the actual API error message instead of assuming
                            raise Exception(f"Cannot remove member: {error_message}")
                    elif 'permission' in error_message.lower() or 'not allowed' in error_message.lower() or 'forbidden' in error_message.lower():
                        raise Exception(f"You don't have permission to remove members from this channel: {error_message}")
                    elif 'not found' in error_message.lower():
                        raise Exception(f"Member not found in the channel: {error_message}")
                    else:
                        # Return the actual API error message
                        raise Exception(f"Failed to remove member: {error_message}")
                except (json.JSONDecodeError, KeyError, AttributeError):
                    # Fallback to text-based checks if JSON parsing fails
                    error_text_lower = error_text.lower()
                    if "operation not supported" in error_text_lower:
                        if "general" in error_text_lower:
                            raise Exception("Cannot remove members from the General channel. The General channel always includes all team members.")
                        else:
                            raise Exception(f"Cannot remove member: {error_text}")
                    elif "not allowed" in error_text_lower or "forbidden" in error_text_lower:
                        raise Exception("You don't have permission to remove members from this channel.")
                    elif "not found" in error_text_lower:
                        raise Exception("Member not found in the channel.")
                    else:
                        raise Exception(f"Failed to remove member: {error_text}")
            else:
                raise Exception(f"Failed to remove member: {str(e)}")

    def remove_team_member(self, team_id: str, member_id: str) -> bool:
        """
        Remove a user from a team.
        
        Args:
            team_id (str): Team ID
            member_id (str): Member ID to remove
            
        Returns:
            bool: True if user was removed successfully, False otherwise
        """
        try:
            endpoint = f'/teams/{team_id}/members/{member_id}'
            
            response = self.graph_api.delete(endpoint)
            
            # Check if the response is a Response object
            if hasattr(response, 'status_code'):
                success = response.status_code in [200, 201, 204]
                
                return success
            else:
                return False
            
        except Exception as e:
            if hasattr(e, 'response') and hasattr(e.response, 'text'):
                error_text = e.response.text
                
                # Check for specific error messages
                if "last owner" in error_text.lower():
                    raise Exception("Cannot remove the last owner of the team. Teams must have at least one owner.")
                elif "not allowed" in error_text.lower():
                    raise Exception("You don't have permission to remove this member.")
                elif "not found" in error_text.lower():
                    raise Exception("Member not found in the team.")
                else:
                    # Try to parse JSON error
                    try:
                        import json
                        error_data = json.loads(error_text)
                        error_message = error_data.get('error', {}).get('message', str(e))
                        raise Exception(error_message)
                    except (json.JSONDecodeError, KeyError, AttributeError):
                        raise Exception(f"Failed to remove member: {str(e)}")
            else:
                raise Exception(f"Failed to remove member: {str(e)}")
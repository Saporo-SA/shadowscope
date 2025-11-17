"""
Graph API Notifications module for managing Microsoft Graph change notifications.
"""

from typing import Dict, List, Optional, Any
from datetime import datetime
import logging
from flask import current_app

from app.utils.graph_api import GraphAPI

logger = logging.getLogger(__name__)


class GraphNotifications:
    """
    Microsoft Graph API Notifications management class.
    
    Handles creation, listing, and deletion of change notification subscriptions
    for monitoring Microsoft 365 resources in real-time.
    """
    
    def __init__(self, token: str):
        """
        Initialize Graph Notifications manager with authentication token.
        
        Args:
            token (str): Microsoft Graph API access token
        """
        self.token = token
        self.graph_api = GraphAPI(token)
        self.graph_api_beta = GraphAPI(token, use_beta=True)
    
    def create_subscription(self, notification_url: str, resource: str, 
                          expiration_datetime: str, client_state: str = None, keywords: List[str] = None) -> Dict[str, Any]:
        """
        Create a new change notification subscription.
        
        Args:
            notification_url (str): URL to receive notifications
            resource (str): Resource to monitor (e.g., '/teams/getAllMessages')
            expiration_datetime (str): ISO datetime string for expiration
            client_state (str): Optional client state for validation
            keywords (List[str]): Optional keywords for filtering messages
            
        Returns:
            Dict with operation result
        """
        try:
            # Generate client state if not provided
            if not client_state:
                import uuid
                client_state = str(uuid.uuid4())
            
            # Clean notification URL (remove trailing slash)
            clean_notification_url = notification_url.rstrip('/')
            
            # Prepare subscription payload
            subscription_payload = {
                "changeType": "created,updated",
                "notificationUrl": f"{clean_notification_url}/api/webhook",
                "lifecycleNotificationUrl": f"{clean_notification_url}/api/lifecycle",
                "resource": f"/{resource}",
                "expirationDateTime": expiration_datetime,
                "clientState": client_state
            }
            
            # Add $search parameter to resource if keywords are provided for teams/getAllMessages and chats/getAllMessages
            if keywords and (resource == "teams/getAllMessages" or resource == "chats/getAllMessages"):
                search_terms = " OR ".join([f'"{keyword}"' for keyword in keywords])
                subscription_payload["resource"] = f"/{resource}?$search={search_terms}"
            
            # Use beta endpoint for Copilot resources and chats (1:1 chats require beta)
            use_beta_api = 'copilot' in resource.lower() or 'chats' in resource.lower()
            api_client = self.graph_api_beta if use_beta_api else self.graph_api
            
            if use_beta_api:
                if 'copilot' in resource.lower():
                    current_app.logger.info("Using /beta endpoint for Copilot resource")
                elif 'chats' in resource.lower():
                    current_app.logger.info("Using /beta endpoint for chats (1:1 chats require beta endpoint)")
            
            current_app.logger.info(f"Creating subscription with payload: {subscription_payload}")
            current_app.logger.info(f"Using API endpoint: {'beta' if use_beta_api else 'v1.0'}")
            
            response = api_client.post('subscriptions', subscription_payload)
            
            current_app.logger.info(f"Subscription creation response status: {response.status_code}")
            if response.status_code != 201:
                current_app.logger.error(f"Subscription creation failed. Response: {response.text}")
            
            if response.status_code == 201:
                subscription_data = response.json()
                
                return {
                    'success': True,
                    'message': 'Subscription created successfully',
                    'data': subscription_data
                }
            else:
                error_message = f"Failed to create subscription: {response.status_code}"
                error_details = []
                
                if response.text:
                    try:
                        error_data = response.json()
                        error_obj = error_data.get('error', {})
                        error_message = error_obj.get('message', error_message)
                        error_code = error_obj.get('code', 'Unknown')
                        error_details = error_obj.get('details', [])
                        
                        # Provide concise error messages for pop-ups
                        if 'ExtensionError' in error_code or 'ExtensionError' in error_message:
                            # Check if it's a specific permission error for chat subscriptions
                            if 'Chat.Read.All' in error_message or 'Chat.ReadWrite.All' in error_message or 'tenant-wide chat message subscription' in error_message:
                                error_message = "Chat subscriptions require Chat.Read.All or Chat.ReadWrite.All. ChatMessage.Read.All is not sufficient."
                            else:
                                # Generic ExtensionError - extract main message
                                error_message = f"ExtensionError: {error_message[:100]}" if len(error_message) > 100 else f"ExtensionError: {error_message}"
                        elif 'Copilot licenses provisioned' in error_message:
                            error_message = "Copilot licenses required. Purchase and assign Copilot licenses to enable this feature."
                        elif 'Invalid notification URL' in error_message or 'NotificationUrlAccessDenied' in error_code:
                            error_message = "Invalid notification URL. Ensure your webhook URL is publicly accessible via HTTPS."
                        elif 'Resource not found' in error_message or 'ResourceNotFound' in error_code:
                            error_message = "Resource not found. Check required permissions."
                        elif 'Invalid resource' in error_message or 'InvalidResource' in error_code:
                            error_message = "Invalid resource type or format."
                        elif 'Forbidden' in error_message or 'Forbidden' in error_code or 'AccessDenied' in error_code:
                            error_message = f"Permission denied ({error_code}). Check Azure AD app permissions and admin consent."
                        elif 'Unauthorized' in error_code:
                            error_message = "Unauthorized. Token may be invalid or expired."
                            
                    except Exception as e:
                        current_app.logger.error(f"Error parsing error response: {str(e)}")
                        error_message = response.text
                
                return {
                    'success': False,
                    'message': error_message,
                    'details': error_details
                }
                
        except Exception as e:
            current_app.logger.error(f"Error creating subscription: {str(e)}")
            return {
                'success': False,
                'message': f'Error creating subscription: {str(e)}'
            }
    
    def list_subscriptions(self) -> Dict[str, Any]:
        """
        List all active subscriptions.
        
        Returns:
            Dict with operation result and subscription list
        """
        try:
            response = self.graph_api.get('subscriptions')
            
            if response:
                subscriptions = response.get('value', [])
                
                # Format subscription data for display
                formatted_subscriptions = []
                for sub in subscriptions:
                    # Try different possible field names for creation date
                    created_datetime = (sub.get('createdDateTime') or 
                                     sub.get('created') or 
                                     sub.get('creationDateTime') or 
                                     sub.get('createdTime'))
                    
                    formatted_sub = {
                        'id': sub.get('id'),
                        'resource': sub.get('resource'),
                        'notification_url': sub.get('notificationUrl'),
                        'created_datetime': created_datetime,
                        'expiration_datetime': sub.get('expirationDateTime'),
                        'client_state': sub.get('clientState'),
                        'change_type': sub.get('changeType'),
                        'status': self._get_subscription_status(sub.get('expirationDateTime'))
                    }
                    formatted_subscriptions.append(formatted_sub)
                
                return {
                    'success': True,
                    'data': formatted_subscriptions
                }
            else:
                return {
                    'success': False,
                    'message': 'Failed to retrieve subscriptions'
                }
                
        except Exception as e:
            current_app.logger.error(f"Error listing subscriptions: {str(e)}")
            return {
                'success': False,
                'message': f'Error listing subscriptions: {str(e)}'
            }
    
    def delete_subscription(self, subscription_id: str) -> Dict[str, Any]:
        """
        Delete a subscription.
        
        Args:
            subscription_id (str): ID of the subscription to delete
            
        Returns:
            Dict with operation result
        """
        try:
            response = self.graph_api.delete(f'subscriptions/{subscription_id}')
            
            if response.status_code == 204:
                return {
                    'success': True,
                    'message': 'Subscription deleted successfully'
                }
            else:
                error_message = f"Failed to delete subscription: {response.status_code}"
                if response.text:
                    try:
                        error_data = response.json()
                        error_message = error_data.get('error', {}).get('message', error_message)
                    except (ValueError, KeyError, TypeError):
                        error_message = response.text
                
                current_app.logger.error(error_message)
                return {
                    'success': False,
                    'message': error_message
                }
                
        except Exception as e:
            current_app.logger.error(f"Error deleting subscription: {str(e)}")
            return {
                'success': False,
                'message': f'Error deleting subscription: {str(e)}'
            }
    
    def renew_subscription(self, subscription_id: str, expiration_minutes: int = 1300) -> Dict[str, Any]:
        """
        Renew a subscription by updating its expiration time.
        
        Args:
            subscription_id (str): ID of the subscription to renew
            expiration_minutes (int): New expiration time in minutes
            
        Returns:
            Dict with operation result
        """
        try:
            # Calculate new expiration datetime
            from datetime import datetime, timedelta
            expiration_datetime = datetime.utcnow() + timedelta(minutes=expiration_minutes)
            expiration_iso = expiration_datetime.strftime('%Y-%m-%dT%H:%M:%S.%fZ')
            
            # Update subscription expiration
            update_payload = {
                "expirationDateTime": expiration_iso
            }
            
            response = self.graph_api.patch(f'subscriptions/{subscription_id}', update_payload)
            
            if response.status_code == 200:
                return {
                    'success': True,
                    'message': 'Subscription renewed successfully',
                    'data': response.json()
                }
            else:
                error_message = f"Failed to renew subscription: {response.status_code}"
                if response.text:
                    try:
                        error_data = response.json()
                        error_message = error_data.get('error', {}).get('message', error_message)
                    except (ValueError, KeyError, TypeError):
                        error_message = response.text
                
                current_app.logger.error(error_message)
                return {
                    'success': False,
                    'message': error_message
                }
                
        except Exception as e:
            current_app.logger.error(f"Error renewing subscription: {str(e)}")
            return {
                'success': False,
                'message': f'Error renewing subscription: {str(e)}'
            }
    
    def _get_subscription_status(self, expiration_datetime: str) -> str:
        """
        Determine subscription status based on expiration time.
        
        Args:
            expiration_datetime (str): ISO datetime string of expiration
            
        Returns:
            str: Status ('Active', 'Expired', 'Expiring Soon')
        """
        try:
            if not expiration_datetime:
                return 'Unknown'
            
            # Parse expiration datetime - handle different microsecond formats
            # Microsoft Graph API can return 5 or 7 decimal places
            datetime_str = expiration_datetime.replace('Z', '+00:00')
            
            # Try parsing directly first
            try:
                exp_dt = datetime.fromisoformat(datetime_str)
            except ValueError:
                # If it fails, try normalizing the microseconds to 6 digits
                import re
                # Match the fractional seconds part
                match = re.search(r'\.(\d+)', datetime_str)
                if match:
                    fractional = match.group(1)
                    # Pad or truncate to 6 digits
                    if len(fractional) < 6:
                        normalized = fractional.ljust(6, '0')
                    else:
                        normalized = fractional[:6]
                    datetime_str = re.sub(r'\.\d+', f'.{normalized}', datetime_str)
                exp_dt = datetime.fromisoformat(datetime_str)
            
            # Get current time with timezone info
            from datetime import timezone
            now = datetime.now(timezone.utc)
            
            # Make sure exp_dt has timezone info
            if exp_dt.tzinfo is None:
                exp_dt = exp_dt.replace(tzinfo=timezone.utc)
            
            # Check if expired
            if exp_dt <= now:
                return 'Expired'
            
            # Check if expiring soon (within 24 hours)
            time_diff = exp_dt - now
            if time_diff.total_seconds() < 86400:  # 24 hours
                return 'Expiring Soon'
            
            return 'Active'
            
        except Exception as e:
            current_app.logger.error(f"Error parsing expiration datetime '{expiration_datetime}': {str(e)}")
            return 'Unknown'
    
    def get_resource_metadata(self, resource_path: str) -> Dict[str, Any]:
        """
        Extract and fetch metadata from resource path (Team/Channel/User names).
        
        Args:
            resource_path (str): Resource path from notification
            
        Returns:
            Dict with type, title, subtitle
        """
        try:
            import re
            
            # Teams Channel Message: teams('team-id')/channels('channel-id')/messages('message-id')
            teams_match = re.search(r"teams\('([^']+)'\)/channels\('([^']+)'\)", resource_path)
            if teams_match:
                team_id = teams_match.group(1)
                channel_id = teams_match.group(2)
                
                try:
                    # Fetch team and channel names
                    team_data = self.graph_api.get(f'teams/{team_id}')
                    channel_data = self.graph_api.get(f'teams/{team_id}/channels/{channel_id}')
                    
                    team_name = team_data.get('displayName', f'Team {team_id[:8]}') if team_data else f'Team {team_id[:8]}'
                    channel_name = channel_data.get('displayName', f'Channel {channel_id[:8]}') if channel_data else f'Channel {channel_id[:8]}'
                    
                    return {
                        'type': 'Teams Channel Message',
                        'title': 'Teams Channel Message',
                        'subtitle': f'Teams: {team_name} → Channel: {channel_name}'
                    }
                except Exception as e:
                    current_app.logger.error(f"Error fetching Teams metadata: {str(e)}")
                    return {
                        'type': 'Teams Channel Message',
                        'title': 'Teams Channel Message',
                        'subtitle': f'Teams: {team_id[:8]}... → Channel: {channel_id[:8]}...'
                    }
            
            # Chat Message: chats('chat-id')/messages('message-id')
            chats_match = re.search(r"chats\('([^']+)'\)", resource_path)
            if chats_match:
                chat_id = chats_match.group(1)
                
                try:
                    # Fetch chat data
                    chat_data = self.graph_api.get(f'chats/{chat_id}')
                    
                    if chat_data:
                        chat_type = chat_data.get('chatType', 'oneOnOne')
                        members_data = self.graph_api.get(f'chats/{chat_id}/members')
                        
                        if members_data and 'value' in members_data:
                            member_names = []
                            for member in members_data.get('value', []):
                                display_name = member.get('displayName')
                                if display_name:
                                    member_names.append(display_name)
                            
                            if chat_type == 'oneOnOne' and len(member_names) >= 2:
                                subtitle = f'{member_names[0]} → {member_names[1]}'
                                return {
                                    'type': 'Chat 1:1 Message',
                                    'title': 'Chat 1:1 Message',
                                    'subtitle': subtitle
                                }
                            elif len(member_names) > 0:
                                subtitle = ' → '.join(member_names)
                                return {
                                    'type': 'Chat Group Message',
                                    'title': 'Chat Group Message',
                                    'subtitle': subtitle
                                }
                    
                    # Fallback
                    return {
                        'type': 'Chat Message',
                        'title': 'Chat Message',
                        'subtitle': f'Chat: {chat_id[:8]}...'
                    }
                except Exception as e:
                    current_app.logger.error(f"Error fetching Chat metadata: {str(e)}")
                    return {
                        'type': 'Chat Message',
                        'title': 'Chat Message',
                        'subtitle': f'Chat: {chat_id[:8]}...'
                    }
            
            # Unknown resource type
            return {
                'type': 'Unknown',
                'title': resource_path[:50],
                'subtitle': resource_path
            }
            
        except Exception as e:
            current_app.logger.error(f"Error extracting resource metadata: {str(e)}")
            return {
                'type': 'Unknown',
                'title': resource_path[:50],
                'subtitle': resource_path
            }
    
    def get_message_content(self, resource_path: str) -> Dict[str, Any]:
        """
        Fetch message content from Teams using the resource path.
        
        Args:
            resource_path (str): Resource path from notification (e.g., teams('id')/channels('id')/messages('id'))
            
        Returns:
            Dict with operation result and message content
        """
        try:
            clean_path = resource_path.lstrip('/')
            
            # Try with v1.0 first
            response = self.graph_api.get(clean_path, raw_response=True)
            
            if response is None:
                return {
                    'success': False,
                    'message': 'Request failed - no response'
                }
            
            # If v1.0 fails with 404, try beta API
            if response.status_code == 404:
                response = self.graph_api_beta.get(clean_path, raw_response=True)
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    return {
                        'success': True,
                        'data': data
                    }
                except Exception as e:
                    return {
                        'success': False,
                        'message': f'Failed to parse response: {str(e)}'
                    }
            else:
                error_msg = f'API returned {response.status_code}'
                try:
                    error_data = response.json()
                    if 'error' in error_data:
                        error_msg += f": {error_data['error'].get('message', 'Unknown error')}"
                except (ValueError, KeyError, TypeError):
                    error_msg += f": {response.text[:200]}"
                
                return {
                    'success': False,
                    'message': error_msg
                }
                
        except Exception as e:
            return {
                'success': False,
                'message': f'Error fetching message: {str(e)}'
            }

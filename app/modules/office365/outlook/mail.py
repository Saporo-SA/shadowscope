from app.utils.graph_api import GraphAPI
from app.utils.route_helpers import format_message_dates
import json
from datetime import datetime
from flask import current_app

class Outlook:
    def __init__(self, graph_api: GraphAPI):
        self.graph_api = graph_api
        
    def list_users_with_mailboxes(self):
        """
        List users that have mailboxes in the organization
        
        Returns:
            list: List of user objects with mailbox information
        """
        try:
            # Get all users with license information
            endpoint = "/users?$select=id,displayName,mail,userPrincipalName,assignedLicenses&$top=999"
            
            all_users = self.graph_api.get_paginated(endpoint)
            
            if not all_users:
                return []
            
            # Get all available license details to identify Office 365 licenses
            license_details = self._get_subscription_skus()
            
            # Map of license IDs to whether they include Exchange Online (mailbox)
            o365_license_ids = set()
            
            # Find licenses that include Exchange Online
            for license in license_details:
                sku_id = license.get('skuId')
                service_plans = license.get('servicePlans', [])
                
                # Check if this license includes Exchange Online
                for plan in service_plans:
                    service_name = plan.get('servicePlanName', '').lower()
                    if 'exchange' in service_name or 'outlook' in service_name:
                        o365_license_ids.add(sku_id)
                        break
            
            # Process users to add additional properties, keeping only those with O365 licenses
            processed_users = []
            for user in all_users:
                user_licenses = user.get('assignedLicenses', [])
                has_mailbox = False
                
                # Check if user has any Office 365 license that includes Exchange Online
                for license in user_licenses:
                    if license.get('skuId') in o365_license_ids:
                        has_mailbox = True
                        break
                
                if has_mailbox:
                    # Add formatted name and other properties
                    processed_user = {
                        'id': user.get('id', ''),
                        'displayName': user.get('displayName', 'Unknown User'),
                        'mail': user.get('mail', ''),
                        'userPrincipalName': user.get('userPrincipalName', ''),
                        'hasMailbox': True,
                    }
                    processed_users.append(processed_user)
                    
            return processed_users
        except Exception as e:
            current_app.logger.error(f"Module - Error listing users with mailboxes: {str(e)}")
            if hasattr(e, 'response') and hasattr(e.response, 'text'):
                current_app.logger.error(f"Module - Response: {e.response.text}")
            return []
            
    def _get_subscription_skus(self):
        """
        Get available subscription SKUs to identify Office 365 licenses
        
        Returns:
            list: List of subscription SKUs
        """
        try:
            response = self.graph_api.get('/subscribedSkus')
            
            if not response or 'value' not in response:
                return []
                
            skus = response.get('value', [])
            return skus
        except Exception as e:
            current_app.logger.error(f"Module - Error fetching subscription SKUs: {str(e)}")
            return []

    def list_messages(self, user_id, folder="inbox", limit=25, skip=0):
        """
        List messages from a specified mail folder
        
        Args:
            user_id (str): The ID of the user whose messages to retrieve
            folder (str): The folder to list messages from (e.g., 'inbox', 'drafts', 'sentitems')
            limit (int): Maximum number of messages to retrieve
            skip (int): Number of messages to skip (for pagination)
            
        Returns:
            list: List of message objects
        """
        try:
            # Build the correct endpoint - always include folder name
            folder_name = "inbox" if folder.lower() == "inbox" else folder
            
            endpoint = f"/users/{user_id}/mailFolders/{folder_name}/messages"
            params = {
                "$top": limit,
                "$skip": skip,
                "$orderby": "receivedDateTime desc",
                "$select": "id,subject,receivedDateTime,from,isRead,bodyPreview,importance,hasAttachments"
            }
            
            response = self.graph_api.get(endpoint, params=params)
            
            if response is None:
                return []
                
            messages = response.get('value', [])
            
            # Process messages for easier template rendering
            for message in messages:
                # Format date
                message = format_message_dates(message)
                        
                # Extract sender name
                if 'from' in message and 'emailAddress' in message['from']:
                    message['senderName'] = message['from']['emailAddress'].get('name', 'Unknown')
                    message['senderEmail'] = message['from']['emailAddress'].get('address', '')
                else:
                    message['senderName'] = 'Unknown'
                    message['senderEmail'] = ''
                    
            return messages
        except Exception as e:
            current_app.logger.error(f"Module - Error listing messages: {str(e)}")
            if hasattr(e, 'response') and hasattr(e.response, 'text'):
                current_app.logger.error(f"Module - Response: {e.response.text}")
            return []

    def get_message(self, user_id, message_id):
        """
        Get a specific message by ID with full body content
        
        Args:
            user_id (str): The ID of the user whose message to retrieve
            message_id (str): The ID of the message to retrieve
            
        Returns:
            dict: Message object with all details including body content
        """
        try:
            endpoint = f"/users/{user_id}/messages/{message_id}"
            params = {
                "$select": "id,subject,receivedDateTime,from,isRead,body,bodyPreview,importance,hasAttachments,toRecipients,ccRecipients,bccRecipients"
            }
            
            response = self.graph_api.get(endpoint, params=params)
            
            if response is None:
                current_app.logger.warning(f"Graph API returned None for message details")
                return None
                
            message = response
            
            # Format date
            message = format_message_dates(message)
                    
            # Extract sender name
            if 'from' in message and 'emailAddress' in message['from']:
                message['senderName'] = message['from']['emailAddress'].get('name', 'Unknown')
                message['senderEmail'] = message['from']['emailAddress'].get('address', '')
            else:
                message['senderName'] = 'Unknown'
                message['senderEmail'] = ''
                
            # Format recipients for display
            message['formatted'] = {
                'to': self._format_recipients(message.get('toRecipients', [])),
                'cc': self._format_recipients(message.get('ccRecipients', [])),
                'bcc': self._format_recipients(message.get('bccRecipients', []))
            }
            
            # Get attachments if there are any
            if message.get('hasAttachments', False):
                message['attachments'] = self.get_message_attachments(user_id, message_id)
            else:
                message['attachments'] = []
                
            return message
        except Exception as e:
            current_app.logger.error(f"Module - Error getting message details: {str(e)}")
            if hasattr(e, 'response') and hasattr(e.response, 'text'):
                current_app.logger.error(f"Module - Response: {e.response.text}")
            return None

    def get_message_attachments(self, user_id, message_id):
        """
        Get attachments for a specific message
        
        Args:
            user_id (str): The ID of the user whose message attachments to retrieve
            message_id (str): The ID of the message
            
        Returns:
            list: List of attachment objects
        """
        try:
            endpoint = f"/users/{user_id}/messages/{message_id}/attachments"
            
            response = self.graph_api.get(endpoint)
            
            if response is None:
                return []
                
            attachments = response.get('value', [])
            return attachments
        except Exception as e:
            current_app.logger.error(f"Module - Error getting attachments: {str(e)}")
            if hasattr(e, 'response') and hasattr(e.response, 'text'):
                current_app.logger.error(f"Module - Response: {e.response.text}")
            return []

    def get_mail_folders(self, user_id):
        """
        Get list of mail folders
        
        Args:
            user_id (str): The ID of the user whose mail folders to retrieve
            
        Returns:
            list: List of mail folder objects
        """
        try:
            endpoint = f"/users/{user_id}/mailFolders"
            params = {
                "$top": 100,
                "$select": "id,displayName,childFolderCount,totalItemCount,unreadItemCount"
            }
            
            response = self.graph_api.get(endpoint, params=params)
            
            if response is None:
                return []
                
            folders = response.get('value', [])
            return folders
        except Exception as e:
            current_app.logger.error(f"Module - Error getting mail folders: {str(e)}")
            if hasattr(e, 'response') and hasattr(e.response, 'text'):
                current_app.logger.error(f"Module - Response: {e.response.text}")
            return []

    def send_email(self, subject, body, to_recipients, cc_recipients=None, bcc_recipients=None, save_to_sent_items=True, user_id=None):
        """
        Send an email message
        
        Args:
            subject (str): Email subject
            body (str): Email body content (HTML format)
            to_recipients (list): List of recipient email addresses
            cc_recipients (list, optional): List of CC recipient email addresses
            bcc_recipients (list, optional): List of BCC recipient email addresses
            save_to_sent_items (bool): Whether to save a copy to sent items folder
            user_id (str, optional): The ID of the user to send mail as. If None, uses /me endpoint.
            
        Returns:
            dict: Result of the operation with success status and message
        """
        try:
            # With application permissions, we must always use /users endpoint
            # /me endpoint is only for delegated permission flows
            if not user_id:
                return {
                    "success": False,
                    "message": "Missing user_id. Cannot use /me endpoint with application permissions."
                }
                
            endpoint = f"/users/{user_id}/sendMail"
            
            # Format recipients
            to_recipients_formatted = [{"emailAddress": {"address": email}} for email in to_recipients]
            
            cc_recipients_formatted = []
            if cc_recipients:
                cc_recipients_formatted = [{"emailAddress": {"address": email}} for email in cc_recipients]
                
            bcc_recipients_formatted = []
            if bcc_recipients:
                bcc_recipients_formatted = [{"emailAddress": {"address": email}} for email in bcc_recipients]
            
            # Create message payload
            payload = {
                "message": {
                    "subject": subject,
                    "body": {
                        "contentType": "HTML",
                        "content": body
                    },
                    "toRecipients": to_recipients_formatted,
                    "ccRecipients": cc_recipients_formatted,
                    "bccRecipients": bcc_recipients_formatted
                },
                "saveToSentItems": save_to_sent_items
            }
            
            response = self.graph_api.post(endpoint, payload=payload)
            
            # Check response status
            success = False
            message = "Failed to send email"
            
            if hasattr(response, 'status_code'):
                # 202 Accepted is the success code for send mail
                if response.status_code in [200, 201, 202, 204]:
                    success = True
                    message = "Email sent successfully"
                else:
                    if hasattr(response, 'text'):
                        try:
                            error_json = json.loads(response.text)
                            if 'error' in error_json:
                                message = error_json['error'].get('message', 'Unknown error')
                        except (ValueError, KeyError, TypeError) as parse_error:
                            current_app.logger.warning(f"Error parsing error response: {parse_error}")
                            pass
            
            return {
                "success": success,
                "message": message
            }
            
        except Exception as e:
            current_app.logger.error(f"Module - Error sending email: {str(e)}")
            error_message = str(e)
            
            if hasattr(e, 'response') and hasattr(e.response, 'text'):
                current_app.logger.error(f"Module - Response: {e.response.text}")
                try:
                    error_json = json.loads(e.response.text)
                    if 'error' in error_json:
                        error_message = error_json['error'].get('message', 'Unknown error')
                except (ValueError, KeyError, TypeError) as parse_error:
                    current_app.logger.warning(f"Error parsing error response: {parse_error}")
                    pass
                    
            return {
                "success": False,
                "message": error_message
            }

    def reply_to_email(self, message_id, body, to_recipients=None, cc_recipients=None, bcc_recipients=None, user_id=None):
        """
        Reply to an existing email
        
        Args:
            message_id (str): ID of the message to reply to
            body (str): Reply body content (HTML format)
            to_recipients (list, optional): List of recipient email addresses (if None, uses original sender)
            cc_recipients (list, optional): List of CC recipient email addresses
            bcc_recipients (list, optional): List of BCC recipient email addresses
            user_id (str, optional): The ID of the user to send mail as. If None, uses /me endpoint.
            
        Returns:
            dict: Result of the operation with success status and message
        """
        try:
            # Get the original message first to get the subject
            # Use the appropriate user context for fetching the message
            if user_id:
                # Get message as specific user
                endpoint = f"/users/{user_id}/messages/{message_id}"
                params = {
                    "$select": "id,subject,from,toRecipients"
                }
                original_message_response = self.graph_api.get(endpoint, params=params)
                
                if not original_message_response:
                    return {
                        "success": False,
                        "message": "Failed to get original message"
                    }
                
                # Format message similar to get_message
                original_message = original_message_response
                
                # Extract sender info
                if 'from' in original_message and 'emailAddress' in original_message['from']:
                    original_message['senderEmail'] = original_message['from']['emailAddress'].get('address', '')
                else:
                    original_message['senderEmail'] = ''
            else:
                # user_id is required with application permissions
                return {
                    "success": False,
                    "message": "user_id is required for application permissions"
                }
                
            if not original_message:
                return {
                    "success": False,
                    "message": "Failed to get original message"
                }
                
            subject = original_message.get('subject', '')
            if not subject.lower().startswith('re:'):
                subject = f"RE: {subject}"
                
            # If no recipients specified, use original sender
            if not to_recipients:
                to_recipients = [original_message.get('senderEmail', '')]
                
            # Use the standard send_email method with user_id
            return self.send_email(subject, body, to_recipients, cc_recipients, bcc_recipients, True, user_id)
            
        except Exception as e:
            current_app.logger.error(f"Module - Error replying to email: {str(e)}")
            return {
                "success": False,
                "message": str(e)
            }

    def _format_recipients(self, recipients):
        """
        Helper method to format email recipients for display
        
        Args:
            recipients (list): List of recipient objects from Graph API
            
        Returns:
            str: Formatted string of recipients
        """
        formatted = []
        for recipient in recipients:
            if 'emailAddress' in recipient:
                name = recipient['emailAddress'].get('name', '')
                address = recipient['emailAddress'].get('address', '')
                if name and name != address:
                    formatted.append(f"{name} <{address}>")
                else:
                    formatted.append(address)
        return "; ".join(formatted)
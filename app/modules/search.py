from typing import Dict, List, Optional, Any
import re
from app.utils.graph_api import GraphAPI
from app.auth.permissions import AzurePermissions
from flask import current_app

class SearchModule:
    def __init__(self, token: str, permissions: AzurePermissions) -> None:
        """
        Initialize the Search module with a Graph API token.
        
        Args:
            token (str): Microsoft Graph API access token
            permissions (AzurePermissions): AzurePermissions instance to check feature access
        """
        self.graph = GraphAPI(token)
        self.graph_beta = GraphAPI(token, use_beta=True)
        self.permissions = permissions
        self.has_chat_permission = self.permissions.has_feature_access('search', 'search_chat_messages')
    
    def _get_region_from_error(self, error_response: Dict) -> Optional[str]:
        """
        Extract correct region from API error response.
        When region is wrong, API returns error with correct region info.
        
        Returns:
            Optional[str]: Region code if found in error, None otherwise
        """
        try:
            error_message = str(error_response.get('error', {}).get('message', ''))
            details = error_response.get('error', {}).get('details', [])
            
            for detail in details:
                detail_msg = str(detail.get('message', ''))
                if 'Only valid regions are' in detail_msg:
                    match = re.search(r'Only valid regions are ([A-Z]{3})', detail_msg)
                    if match:
                        return match.group(1)
            
            if 'Only valid regions are' in error_message:
                match = re.search(r'Only valid regions are ([A-Z]{3})', error_message)
                if match:
                    return match.group(1)
        except Exception:
            pass
        
        return None

    def search_content(self, query: str, page: int = 1, limit: int = 500) -> Dict[str, Any]:
        """
        Search for content across Microsoft 365.
        
        Args:
            query (str): The search query string
            page (int): The page number (1-indexed)
            limit (int): Number of results per page (max 500)
            
        Returns:
            Dict[str, Any]: Dictionary with search results and metadata containing:
                - success (bool): Whether the search was successful
                - results (List[Dict]): List of search result items
                - total (int): Total number of results
                - page (int): Current page number
                - has_more (bool): Whether more results are available
                - errors (Optional[List[str]]): List of error messages if any
        """
        if not query or not query.strip():
            return {
                'success': False,
                'message': 'Search query is required',
                'results': [],
                'total': 0,
                'page': page,
                'has_more': False
            }
            
        # Ensure limit is reasonable
        limit = min(limit, 500)
        
        # Calculate start position for pagination
        start_index = (page - 1) * limit
        
        processed_results = []
        search_errors = []
        has_more = False
        
        def process_search_response(search_results_json, entity_type_filter=None):
            nonlocal has_more
            results = []
            
            if 'value' in search_results_json and len(search_results_json['value']) > 0:
                for search_response in search_results_json['value']:
                    hit_containers = search_response.get('hitsContainers', [])
                    
                    for container in hit_containers:
                        hits = container.get('hits', [])
                        
                        total_obj = container.get('total', {})
                        if isinstance(total_obj, dict):
                            total_count = total_obj.get('count', 0)
                            if total_count > (page * limit):
                                has_more = True
                        
                        for hit in hits:
                            resource = hit.get('resource', {})
                            resource_type = resource.get('@odata.type', '').replace('#microsoft.graph.', '').replace('microsoft.graph.', '')
                            
                            if entity_type_filter and resource_type != entity_type_filter:
                                continue
                            
                            if resource_type == 'driveItem':
                                result_item = {
                                    'type': 'driveItem',
                                    'id': resource.get('id', ''),
                                    'name': resource.get('name', 'Unnamed'),
                                    'created': resource.get('createdDateTime', ''),
                                    'modified': resource.get('lastModifiedDateTime', ''),
                                    'size': resource.get('size', 0),
                                    'icon': 'bi-file-earmark'
                                }
                                
                                parent_ref = resource.get('parentReference', {})
                                drive_id = parent_ref.get('driveId', '')
                                site_id = parent_ref.get('siteId', '')
                                
                                result_item['webUrl'] = resource.get('webUrl', '')
                                
                                if drive_id and result_item['id']:
                                    result_item['url'] = f"/sharepoint/sites/{site_id}/drives/{drive_id}/items/{result_item['id']}/download"
                            
                            elif resource_type == 'chatMessage':
                                from_info = resource.get('from', {})
                                email_address = from_info.get('emailAddress', {}) if isinstance(from_info, dict) else {}
                                
                                result_item = {
                                    'type': 'chatMessage',
                                    'id': resource.get('id', ''),
                                    'name': email_address.get('name', 'Unknown User'),
                                    'created': resource.get('createdDateTime', ''),
                                    'modified': resource.get('lastModifiedDateTime', ''),
                                    'size': 0,
                                    'icon': 'bi-chat-dots',
                                    'webUrl': resource.get('webLink', ''),
                                    'chatId': resource.get('chatId', ''),
                                    'sender': email_address.get('address', '')
                                }
                            
                            else:
                                continue
                            
                            summary = hit.get('summary', '')
                            if summary:
                                clean_summary = re.sub(r'<[^>]+>', ' ', summary)
                                clean_summary = re.sub(r'\s+', ' ', clean_summary).strip()
                                result_item['snippet'] = clean_summary
                            
                            results.append(result_item)
            
            return results
        
        try:
            region = 'NAM'
            
            drive_request = {
                "entityTypes": ["driveItem"],
                "query": {"queryString": query},
                "from": start_index,
                "size": limit,
                "region": region
            }
            
            drive_payload = {"requests": [drive_request]}
            drive_response = self.graph.post('search/query', drive_payload)
            
            if drive_response.status_code == 200:
                drive_results = drive_response.json()
                results = process_search_response(drive_results, entity_type_filter='driveItem')
                processed_results.extend(results)
            elif drive_response.status_code == 400:
                try:
                    error_body = drive_response.json()
                    correct_region = self._get_region_from_error(error_body)
                    
                    if correct_region:
                        drive_request["region"] = correct_region
                        drive_payload = {"requests": [drive_request]}
                        drive_response = self.graph.post('search/query', drive_payload)
                        
                        if drive_response.status_code == 200:
                            drive_results = drive_response.json()
                            results = process_search_response(drive_results, entity_type_filter='driveItem')
                            processed_results.extend(results)
                            region = correct_region
                        else:
                            error_obj = error_body.get('error', {})
                            error_message = error_obj.get('message', 'Drive search failed')
                            search_errors.append(f"Drive search: {error_message}")
                    else:
                        error_obj = error_body.get('error', {})
                        error_message = error_obj.get('message', 'Drive search failed')
                        search_errors.append(f"Drive search: {error_message}")
                except Exception as e:
                    current_app.logger.error(f"Error parsing drive search error response: {e}")
                    search_errors.append("Error parsing drive search error response")
            else:
                try:
                    error_body = drive_response.json()
                    error_obj = error_body.get('error', {})
                    error_message = error_obj.get('message', 'Drive search failed')
                    search_errors.append(f"Drive search: {error_message}")
                except Exception:
                    search_errors.append("Error parsing drive search error response")
            
            if self.has_chat_permission:
                chat_request = {
                    "entityTypes": ["chatMessage"],
                    "query": {"queryString": query},
                    "from": start_index,
                    "size": limit,
                    "region": region
                }
                
                chat_payload = {"requests": [chat_request]}
                chat_response = self.graph_beta.post('search/query', chat_payload)
                
                if chat_response.status_code == 200:
                    chat_results = chat_response.json()
                    results = process_search_response(chat_results, entity_type_filter='chatMessage')
                    processed_results.extend(results)
                elif chat_response.status_code == 400:
                    try:
                        error_body = chat_response.json()
                        correct_region = self._get_region_from_error(error_body)
                        
                        if correct_region:
                            chat_request["region"] = correct_region
                            chat_payload = {"requests": [chat_request]}
                            chat_response = self.graph_beta.post('search/query', chat_payload)
                            
                            if chat_response.status_code == 200:
                                chat_results = chat_response.json()
                                results = process_search_response(chat_results, entity_type_filter='chatMessage')
                                processed_results.extend(results)
                            else:
                                error_obj = error_body.get('error', {})
                                error_message = error_obj.get('message', 'Chat search failed')
                                search_errors.append(f"Chat search: {error_message}")
                        else:
                            error_obj = error_body.get('error', {})
                            error_message = error_obj.get('message', 'Chat search failed')
                            search_errors.append(f"Chat search: {error_message}")
                    except Exception as e:
                        current_app.logger.error(f"Error parsing chat search error response: {e}")
                        search_errors.append("Error parsing chat search error response")
                elif chat_response.status_code == 403:
                    error_body = chat_response.json()
                    error_obj = error_body.get('error', {})
                    error_message = error_obj.get('message', '')
                    if 'Application permission' not in error_message or 'chatMessage' not in error_message.lower():
                        search_errors.append(f"Chat search: {error_message}")
                else:
                    try:
                        error_body = chat_response.json()
                        error_obj = error_body.get('error', {})
                        error_message = error_obj.get('message', 'Chat search failed')
                        search_errors.append(f"Chat search: {error_message}")
                    except Exception:
                        search_errors.append("Error parsing chat search error response")
                    
        except Exception as e:
            search_errors.append(f"Exception searching: {str(e)}")
        
        # Return processed results and metadata
        return {
            'success': True,
            'results': processed_results,
            'total': len(processed_results),
            'page': page,
            'has_more': has_more,
            'errors': search_errors if search_errors else None
        }
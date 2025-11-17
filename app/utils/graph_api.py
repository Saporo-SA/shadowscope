import requests
from typing import List, Dict, Union, Optional, Any

class GraphAPI:
    """
    Microsoft Graph API client for making authenticated requests.
    
    This class provides methods to interact with Microsoft Graph API endpoints
    including GET, POST, PATCH, and DELETE operations with automatic pagination support.
    """
    
    def __init__(self, access_token: str, use_beta: bool = False) -> None:
        """
        Initialize the GraphAPI client with an access token.
        
        Args:
            access_token (str): Microsoft Graph API access token
            use_beta (bool): Use beta endpoint instead of v1.0 (default: False)
        """
        self.headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        api_version = "beta" if use_beta else "v1.0"
        self.base_url = f"https://graph.microsoft.com/{api_version}"

    def get(self, endpoint: str, params: Optional[Dict[str, Any]] = None, raw_response: bool = False, custom_headers: Optional[Dict[str, str]] = None) -> Union[Dict[str, Any], requests.Response, None]:
        """
        Make a GET request to the Microsoft Graph API.
        
        Args:
            endpoint (str): The API endpoint to call (without base URL)
            params (Optional[Dict[str, Any]]): Query parameters to include
            raw_response (bool): If True, return the raw Response object instead of JSON
            custom_headers (Optional[Dict[str, str]]): Custom headers to merge with instance headers
            
        Returns:
            Union[Dict[str, Any], requests.Response, None]: JSON response, Response object, or None on error
        """
        url = f"{self.base_url}/{endpoint}"
        merged_headers = {**self.headers}
        if custom_headers:
            merged_headers.update(custom_headers)
        
        try:
            response = requests.get(url, headers=merged_headers, params=params)
            
            if raw_response:
                return response
                
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException:
            return None

    def post(self, endpoint: str, payload: Dict[str, Any], custom_headers: Optional[Dict[str, str]] = None) -> requests.Response:
        """
        Make a POST request to the Microsoft Graph API.
        
        Args:
            endpoint (str): The API endpoint to call (without base URL)
            payload (Dict[str, Any]): JSON payload to send in the request body
            custom_headers (Optional[Dict[str, str]]): Custom headers to merge with instance headers
            
        Returns:
            requests.Response: The HTTP response object
        """
        url = f"{self.base_url}/{endpoint}"
        merged_headers = {**self.headers}
        if custom_headers:
            merged_headers.update(custom_headers)
        
        response = requests.post(url, headers=merged_headers, json=payload)
        
        # Check for HTML response indicating session expiration
        if response.text.strip().startswith(('<!doctype', '<html')):
            response.status_code = 401
        
        return response

    def patch(self, endpoint: str, payload: Dict[str, Any], custom_headers: Optional[Dict[str, str]] = None) -> requests.Response:
        """
        Make a PATCH request to the Microsoft Graph API.
        
        Args:
            endpoint (str): The API endpoint to call (without base URL)
            payload (Dict[str, Any]): JSON payload to send in the request body
            custom_headers (Optional[Dict[str, str]]): Custom headers to merge with instance headers
            
        Returns:
            requests.Response: The HTTP response object
        """
        url = f"{self.base_url}/{endpoint}"
        merged_headers = {**self.headers}
        if custom_headers:
            merged_headers.update(custom_headers)
        
        try:
            response = requests.patch(url, headers=merged_headers, json=payload)
            
            # Check for HTML response indicating session expiration
            if response.text.strip().startswith(('<!doctype', '<html')):
                response.status_code = 401
                return response
                
            response.raise_for_status()
            return response
                
        except requests.exceptions.RequestException as e:
            if hasattr(e, 'response') and e.response is not None:
                if e.response.text.strip().startswith(('<!doctype', '<html')):
                    e.response.status_code = 401
            raise

    def delete(self, endpoint: str, custom_headers: Optional[Dict[str, str]] = None) -> requests.Response:
        """
        Make a DELETE request to the Microsoft Graph API.
        
        Args:
            endpoint (str): The API endpoint to call (without base URL)
            custom_headers (Optional[Dict[str, str]]): Custom headers to merge with instance headers
            
        Returns:
            requests.Response: The HTTP response object
        """
        url = f"{self.base_url}/{endpoint}"
        merged_headers = {**self.headers}
        if custom_headers:
            merged_headers.update(custom_headers)
        
        try:
            response = requests.delete(url, headers=merged_headers)
            
            # Check for HTML response indicating session expiration
            if response.text.strip().startswith(('<!doctype', '<html')):
                response.status_code = 401
                return response
                
            response.raise_for_status()
            return response
        except requests.exceptions.RequestException as e:
            if hasattr(e, 'response') and e.response is not None:
                if e.response.text.strip().startswith(('<!doctype', '<html')):
                    e.response.status_code = 401
            raise

    def get_paginated(self, endpoint: str, params: Optional[Dict[str, Any]] = None, custom_headers: Optional[Dict[str, str]] = None) -> List[Dict[str, Any]]:
        """
        Get paginated results from Microsoft Graph API.
        
        Args:
            endpoint (str): The API endpoint to call (without base URL)
            params (Optional[Dict[str, Any]]): Query parameters to include
            custom_headers (Optional[Dict[str, str]]): Custom headers to merge with instance headers
            
        Returns:
            List[Dict[str, Any]]: List of all results from all pages
        """
        results = []
        
        if endpoint.startswith('/'):
            endpoint = endpoint[1:]
        
        url = f"{self.base_url}/{endpoint}"
        page_count = 0
        
        merged_headers = {**self.headers}
        if custom_headers:
            merged_headers.update(custom_headers)
        
        with requests.Session() as session:
            session.headers.update(merged_headers)
            
            while url:
                try:
                    if page_count == 0 and params:
                        response = session.get(url, params=params, timeout=60)
                    else:
                        response = session.get(url, timeout=60)
                    
                    response.raise_for_status()
                    data = response.json()
                    page_values = data.get("value", [])
                    results.extend(page_values)
                    
                    url = data.get("@odata.nextLink")
                    page_count += 1
                        
                except requests.exceptions.RequestException:
                    break
        
        return results
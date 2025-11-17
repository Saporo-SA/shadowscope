from app.utils.graph_api import GraphAPI
import json
import time
from typing import List, Dict, Any, Optional, Union

class SharePoint:
    def __init__(self, graph_api: GraphAPI):
        self.graph = graph_api
        self.last_error = None

    def list_sites(self) -> List[Dict[str, Any]]:
        """
        List all available SharePoint sites in the tenant
        """
        try:
            # First, get root SharePoint site
            root_site = self.graph.get('/sites/root')
            if not root_site:
                return []
                
            # Get sites collection
            result = self.graph.get('/sites?search=*')
            if not result or 'value' not in result:
                return []
                
            sites = result.get('value', [])
            
            # Process sites to add additional metadata if needed
            for site in sites:
                # Add any additional processing here if needed
                pass
                
            return sites
        except Exception as e:
            self.last_error = str(e)
            return []

    def get_site_details(self, site_id: str) -> Optional[Dict[str, Any]]:
        """
        Get detailed information about a specific SharePoint site
        """
        try:
            site = self.graph.get(f'/sites/{site_id}')
            return site
        except Exception as e:
            self.last_error = str(e)
            return None

    def list_site_drives(self, site_id: str) -> List[Dict[str, Any]]:
        """
        List all drives (document libraries) in a SharePoint site
        """
        try:
            result = self.graph.get(f'/sites/{site_id}/drives')
            if not result or 'value' not in result:
                return []
                
            return result.get('value', [])
        except Exception as e:
            self.last_error = str(e)
            return []
            
    def list_drive_items(self, drive_id: str, item_path: str = '') -> List[Dict[str, Any]]:
        """
        List items in a drive or within a folder in a drive
        
        Args:
            drive_id: The ID of the drive
            item_path: Optional path to a folder within the drive
        """
        try:
            # If item_path is provided, get items from that folder, otherwise get root items
            endpoint = f'/drives/{drive_id}/root/children'
            if item_path and item_path != '/':
                # Need to ensure the path is properly formatted
                if item_path.startswith('/'):
                    item_path = item_path[1:]
                endpoint = f'/drives/{drive_id}/root:/{item_path}:/children'
                
            result = self.graph.get(endpoint)
            if not result or 'value' not in result:
                return []
                
            items = result.get('value', [])
            
            # Get download URL for each file if not already provided
            for item in items:
                if item.get('file') and not item.get('@microsoft.graph.downloadUrl'):
                    try:
                        # Get the download URL for this file
                        item_id = item.get('id')
                        if item_id:
                            download_info = self.graph.get(f'/drives/{drive_id}/items/{item_id}')
                            if download_info and download_info.get('@microsoft.graph.downloadUrl'):
                                item['@microsoft.graph.downloadUrl'] = download_info.get('@microsoft.graph.downloadUrl')
                    except Exception as e:
                        pass  # Error getting download URL, continue with other items
                
            return items
        except Exception as e:
            self.last_error = str(e)
            return []
            
    def get_download_url(self, drive_id: str, item_id: str) -> Optional[str]:
        """
        Get download URL for a file in a drive
        
        Args:
            drive_id: The ID of the drive
            item_id: The ID of the file
        """
        try:
            result = self.graph.get(f'/drives/{drive_id}/items/{item_id}')
            if result and result.get('@microsoft.graph.downloadUrl'):
                return result.get('@microsoft.graph.downloadUrl')
            return None
        except Exception as e:
            self.last_error = str(e)
            return None
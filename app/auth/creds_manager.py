"""
Credentials Manager for ShadowScope
Manages temporary .creds file for token auto-refresh during active sessions
"""

import os
import json
from typing import Optional, Dict
from pathlib import Path


class CredsManager:
    """Manages temporary credentials file for auto-refresh functionality"""
    
    CREDS_FILE = '.creds'
    CREDS_PATH = Path(__file__).parent.parent.parent / CREDS_FILE
    
    @classmethod
    def save_credentials(cls, tenant_id: str, client_id: str, client_secret: str) -> bool:
        """
        Save credentials to .creds file
        
        Args:
            tenant_id: Azure tenant ID
            client_id: Service Principal client ID
            client_secret: Service Principal client secret
            
        Returns:
            bool: True if saved successfully, False otherwise
        """
        try:
            creds_data = {
                'tenant_id': tenant_id,
                'client_id': client_id,
                'client_secret': client_secret
            }
            
            with open(cls.CREDS_PATH, 'w') as f:
                json.dump(creds_data, f, indent=2)
            
            os.chmod(cls.CREDS_PATH, 0o600)
            
            return True
        except Exception as e:
            from flask import current_app
            try:
                current_app.logger.error(f"Error saving credentials: {str(e)}")
            except RuntimeError:
                pass
            return False
    
    @classmethod
    def load_credentials(cls) -> Optional[Dict[str, str]]:
        """
        Load credentials from .creds file
        
        Returns:
            Dict with tenant_id, client_id, client_secret or None if file doesn't exist
        """
        try:
            if not cls.CREDS_PATH.exists():
                return None
            
            with open(cls.CREDS_PATH, 'r') as f:
                creds_data = json.load(f)
            
            if all(k in creds_data for k in ['tenant_id', 'client_id', 'client_secret']):
                return creds_data
            
            return None
        except Exception as e:
            from flask import current_app
            try:
                current_app.logger.error(f"Error loading credentials: {str(e)}")
            except RuntimeError:
                pass
            return None
    
    @classmethod
    def delete_credentials(cls) -> bool:
        """
        Delete .creds file
        
        Returns:
            bool: True if deleted successfully, False otherwise
        """
        try:
            if cls.CREDS_PATH.exists():
                cls.CREDS_PATH.unlink()
                return True
            return False
        except Exception as e:
            from flask import current_app
            try:
                current_app.logger.error(f"Error deleting credentials: {str(e)}")
            except RuntimeError:
                pass
            return False
    
    @classmethod
    def credentials_exist(cls) -> bool:
        """
        Check if .creds file exists
        
        Returns:
            bool: True if file exists, False otherwise
        """
        return cls.CREDS_PATH.exists()


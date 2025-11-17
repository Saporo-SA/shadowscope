"""
Archive utilities for ShadowScope
Handles archiving of results folder on logout
"""

import os
import zipfile
import datetime
import logging
from typing import Optional
from pathlib import Path

# Set up logging for when not in Flask context
logger = logging.getLogger(__name__)


def archive_results_folder() -> Optional[str]:
    """
    Archive all files in the results folder into a zip file and delete the original files.
    
    Returns:
        Optional[str]: Path to the created zip file, or None if no files to archive
    """
    try:
        results_dir = Path("results")
        
        # Check if results directory exists and has files
        if not results_dir.exists() or not any(results_dir.iterdir()):
            logger.info("No files found in results directory to archive")
            return None
        
        # Create timestamp for unique filename
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        zip_filename = f"results_archive_{timestamp}.zip"
        zip_path = results_dir / zip_filename
        
        # Create zip file
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for file_path in results_dir.iterdir():
                if file_path.is_file() and not file_path.name.endswith('.zip'):
                    # Add file to zip with relative path
                    zipf.write(file_path, file_path.name)
        
        # Delete original files (but keep the zip file)
        files_deleted = 0
        for file_path in results_dir.iterdir():
            if file_path.is_file() and not file_path.name.endswith('.zip'):
                file_path.unlink()
                files_deleted += 1
        
        logger.info(f"Archived {files_deleted} files into {zip_filename}")
        return str(zip_path)
        
    except Exception as e:
        logger.error(f"Error archiving results folder: {str(e)}")
        return None


def cleanup_old_archives(max_archives: int = 10) -> None:
    """
    Clean up old archive files, keeping only the most recent ones.
    
    Args:
        max_archives (int): Maximum number of archive files to keep
    """
    try:
        results_dir = Path("results")
        
        if not results_dir.exists():
            return
        
        # Get all zip files sorted by modification time (newest first)
        zip_files = sorted(
            [f for f in results_dir.glob("results_archive_*.zip")],
            key=lambda x: x.stat().st_mtime,
            reverse=True
        )
        
        # Delete old archives if we have more than max_archives
        if len(zip_files) > max_archives:
            files_to_delete = zip_files[max_archives:]
            for file_path in files_to_delete:
                file_path.unlink()
                logger.info(f"Deleted old archive: {file_path.name}")
                
    except Exception as e:
        logger.error(f"Error cleaning up old archives: {str(e)}")

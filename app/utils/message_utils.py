"""
Message utility functions for processing Graph API messages.
"""


def process_message(msg):
    """
    Process and normalize a message object from Graph API.
    
    Ensures required fields exist with default values to prevent errors
    when rendering messages in the frontend.
    
    Args:
        msg (dict): Raw message object from Graph API
        
    Returns:
        dict: Processed message with guaranteed 'from' and 'body' fields
    """
    if 'from' not in msg or not msg['from']:
        msg['from'] = {'user': {'displayName': 'Unknown'}}
    elif 'user' not in msg['from'] or not msg['from']['user']:
        msg['from']['user'] = {'displayName': 'Unknown'}
    
    if 'body' not in msg or not msg['body']:
        msg['body'] = {'content': 'No content'}
    
    return msg


def sort_messages_chronologically(messages):
    """
    Sort messages by creation date in ascending order (oldest first).
    
    Args:
        messages (list): List of message objects with 'createdDateTime' field
        
    Returns:
        list: Sorted list of messages
    """
    return sorted(messages, key=lambda x: x.get('createdDateTime', ''))


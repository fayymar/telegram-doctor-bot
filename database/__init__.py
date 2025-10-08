"""
Database module for Telegram Medical Bot
"""

from .connection import supabase_client
from .models import UserProfile, Consultation, Message

__all__ = ['supabase_client', 'UserProfile', 'Consultation', 'Message']

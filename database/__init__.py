"""
Database module for Telegram Medical Bot
"""

from .connection import supabase_client
from .models import Consultation, Message, UserProfile

__all__ = ['Consultation', 'Message', 'UserProfile', 'supabase_client']

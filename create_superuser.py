#!/usr/bin/env python
"""
Script to create or update Django superuser
Usage: 
  python create_superuser.py [username] [password] [email]
  Or set environment variables: DJANGO_SUPERUSER_USERNAME, DJANGO_SUPERUSER_PASSWORD, DJANGO_SUPERUSER_EMAIL
  Or password will be prompted if not provided
"""
import os
import sys
import getpass
import django

# Setup Django
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()

from django.contrib.auth import get_user_model

User = get_user_model()

def create_or_update_superuser(username=None, password=None, email=None):
    """Create or update a superuser"""
    try:
        # Get username
        if not username:
            username = os.environ.get('DJANGO_SUPERUSER_USERNAME', 'admin')
        
        # Get password - NEVER use default password
        if not password:
            password = os.environ.get('DJANGO_SUPERUSER_PASSWORD')
            if not password:
                # Prompt for password if not in environment
                password = getpass.getpass(f'Enter password for superuser "{username}": ')
                if not password:
                    print("✗ Error: Password is required")
                    sys.exit(1)
        
        # Get email
        if not email:
            email = os.environ.get('DJANGO_SUPERUSER_EMAIL', f'{username}@example.com')
        
        user = User.objects.filter(username=username).first()
        
        if user:
            print(f"User '{username}' already exists. Updating...")
            user.set_password(password)
            user.is_superuser = True
            user.is_staff = True
            user.is_active = True
            if hasattr(user, 'email'):
                user.email = email
            if hasattr(user, 'role'):
                user.role = 'admin'
            user.save()
            print(f"✓ Updated user '{username}' successfully")
        else:
            print(f"Creating new superuser '{username}'...")
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password,
                is_superuser=True,
                is_staff=True,
                is_active=True
            )
            if hasattr(user, 'role'):
                user.role = 'admin'
                user.save()
            print(f"✓ Created superuser '{username}' successfully (ID: {user.id})")
        
        print(f"\n=== User Details ===")
        print(f"Username: {user.username}")
        print(f"Email: {getattr(user, 'email', 'N/A')}")
        print(f"Is Superuser: {user.is_superuser}")
        print(f"Is Staff: {user.is_staff}")
        print(f"Is Active: {user.is_active}")
        if hasattr(user, 'role'):
            print(f"Role: {user.role}")
        
        return user
    except Exception as e:
        print(f"✗ Error: {e}")
        sys.exit(1)

if __name__ == '__main__':
    username = sys.argv[1] if len(sys.argv) > 1 else None
    password = sys.argv[2] if len(sys.argv) > 2 else None
    email = sys.argv[3] if len(sys.argv) > 3 else None
    
    create_or_update_superuser(username, password, email)



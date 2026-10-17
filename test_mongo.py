"""Diagnostic script to test MongoDB Atlas connectivity and Django ORM integration."""
import os
import sys

# Ensure settings are loaded
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django
django.setup()

from django.conf import settings
from django.db import connection
from flights.services.mongo import check_mongo_connection
from flights.models import Booking, UserProfile
from django.contrib.auth import get_user_model

def main():
    print("=" * 60)
    print("  Flight Portal MongoDB Connectivity Test")
    print("=" * 60)
    
    print(f"\n1. Settings Configuration:")
    print(f"   - Database Engine: {settings.DATABASES['default']['ENGINE']}")
    print(f"   - Database Name:   {settings.DATABASES['default']['NAME']}")
    print(f"   - Default Auto Field: {settings.DEFAULT_AUTO_FIELD}")
    print(f"   - Router:          {getattr(settings, 'DATABASE_ROUTERS', [])}")
    
    print(f"\n2. PyMongo Direct Connection Test:")
    res = check_mongo_connection()
    if res["connected"]:
        print(f"   [SUCCESS] Connected to MongoDB Atlas!")
        print(f"   - Database: {res['database']}")
        print(f"   - Collections ({len(res['collections'])} found):")
        for c in res['collections']:
            print(f"       * {c}")
            
        print(f"\n3. Django ORM Backend Test:")
        try:
            User = get_user_model()
            user_count = User.objects.count()
            booking_count = Booking.objects.count()
            print(f"   [SUCCESS] Django ORM is active on MongoDB!")
            print(f"   - Total Users in MongoDB: {user_count}")
            print(f"   - Total Bookings in MongoDB: {booking_count}")
        except Exception as e:
            print(f"   [FAILED] Django ORM query failed: {e}")
            sys.exit(1)
            
        print("\n" + "=" * 60)
        print("  All MongoDB integration checks PASSED successfully!")
        print("=" * 60)
    else:
        print(f"   [FAILED] Could not connect via PyMongo:")
        print(f"   - Raw Error: {res['error'][:140]}...")
        if res.get("diagnosis"):
            print(f"\n   [DIAGNOSIS & ACTION REQUIRED]:")
            for line in res["diagnosis"].splitlines():
                print(f"   {line}")
        
        print("\n" + "-" * 60)
        print("  ALTERNATIVE: Run with SQLite Database Fallback")
        print("  If you want to run the portal immediately without Atlas:")
        print("  Set USE_MONGODB=0 in .env or run:")
        print("    $env:USE_MONGODB='0'; python app.py")
        print("  or:")
        print("    $env:USE_MONGODB='0'; python manage.py runserver")
        print("-" * 60)

if __name__ == "__main__":
    main()

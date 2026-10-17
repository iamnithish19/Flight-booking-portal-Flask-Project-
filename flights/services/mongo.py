"""MongoDB Client Helper Service
Provides a clean interface for direct PyMongo operations alongside Django ORM.
"""
import os
import socket
import urllib.request
from functools import lru_cache
from typing import Any, Dict
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(BASE_DIR / ".env", override=False)

from pymongo import MongoClient
import certifi

# Force IPv4 resolution for MongoDB Atlas hosts (Atlas clusters do not support IPv6/NAT64)
_orig_getaddrinfo = socket.getaddrinfo

def _ipv4_preferring_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    try:
        res = _orig_getaddrinfo(host, port, family, type, proto, flags)
        if host and "mongodb.net" in str(host):
            v4 = [r for r in res if r[0] == socket.AF_INET]
            if v4:
                return v4
        return res
    except Exception:
        return _orig_getaddrinfo(host, port, family, type, proto, flags)

socket.getaddrinfo = _ipv4_preferring_getaddrinfo

# DNS fallback for Windows / SRV resolution - only IPv4 nameservers to avoid IPv6 NAT64 issues
try:
    import dns.resolver
    _res = dns.resolver.get_default_resolver()
    for _ns in ["8.8.8.8", "1.1.1.1"]:
        if _ns not in _res.nameservers:
            _res.nameservers.append(_ns)
except Exception:
    pass

_CLIENT: MongoClient | None = None


def get_mongo_uri() -> str:
    return os.environ.get("MONGODB_URI", "").strip()


def get_mongo_db_name() -> str:
    return os.environ.get("MONGODB_NAME", "flight_portal").strip()


def get_mongo_client() -> MongoClient:
    global _CLIENT
    if _CLIENT is None:
        uri = get_mongo_uri()
        if not uri:
            raise ValueError("MONGODB_URI is not set in environment or settings.")
        _CLIENT = MongoClient(
            uri,
            serverSelectionTimeoutMS=5000,
            tlsCAFile=certifi.where(),
        )
    return _CLIENT


def get_mongo_db(db_name: str | None = None):
    client = get_mongo_client()
    return client[db_name or get_mongo_db_name()]


def get_public_ip() -> str:
    for url in ["https://api.ipify.org", "https://checkip.amazonaws.com", "https://ifconfig.me/ip"]:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "curl/7.68.0"})
            with urllib.request.urlopen(req, timeout=3) as resp:
                return resp.read().decode("utf-8").strip()
        except Exception:
            continue
    return "Unknown"


_MONGO_STATUS: bool | None = None


def is_mongo_available(force_refresh: bool = False) -> bool:
    """Checks if MongoDB is configured and currently reachable."""
    global _MONGO_STATUS
    if _MONGO_STATUS is not None and not force_refresh:
        return _MONGO_STATUS

    use_mongo = os.environ.get("USE_MONGODB", "1").lower() in ("1", "true", "yes")
    uri = get_mongo_uri()
    if not use_mongo or not uri:
        _MONGO_STATUS = False
        return False

    try:
        client = get_mongo_client()
        client.admin.command("ping")
        _MONGO_STATUS = True
        return True
    except Exception:
        _MONGO_STATUS = False
        return False


def check_mongo_connection() -> Dict[str, Any]:
    """Tests connection to MongoDB and returns status report."""
    try:
        client = get_mongo_client()
        ping_res = client.admin.command("ping")
        db = get_mongo_db()
        collections = db.list_collection_names()
        return {
            "connected": True,
            "ping": ping_res,
            "database": db.name,
            "collections": sorted(collections),
            "error": None,
            "diagnosis": None,
        }
    except Exception as exc:
        err_msg = str(exc)
        diagnosis = None
        if "TLSV1_ALERT_INTERNAL_ERROR" in err_msg or "SSL alert number 80" in err_msg:
            pub_ip = get_public_ip()
            diagnosis = (
                f"MongoDB Atlas rejected the TLS handshake (TLS Alert 80: Internal Error).\n"
                f"   This indicates your current public IP ({pub_ip}) is NOT in the MongoDB Atlas\n"
                f"   Network Access IP Whitelist.\n\n"
                f"   Steps to resolve in Atlas:\n"
                f"   1. Open: https://cloud.mongodb.com/\n"
                f"   2. Go to 'Security' -> 'Network Access'\n"
                f"   3. Click 'Add IP Address'\n"
                f"   4. Click 'Add Current IP Address' ({pub_ip}) or enter '0.0.0.0/0' for all\n"
                f"   5. Click 'Confirm' and wait 1 minute for it to apply."
            )
        return {
            "connected": False,
            "ping": None,
            "database": get_mongo_db_name(),
            "collections": [],
            "error": err_msg,
            "diagnosis": diagnosis,
        }

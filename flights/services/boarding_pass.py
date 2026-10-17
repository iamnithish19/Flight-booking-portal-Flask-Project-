import base64
import hashlib
import io
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, Tuple
from PIL import Image
import qrcode
from reportlab.lib import colors
from reportlab.lib.colors import HexColor
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

logger = logging.getLogger(__name__)

# Complete registry of domestic Indian and international airlines
AIRLINE_REGISTRY: Dict[str, dict] = {
    "6E": {
        "name": "IndiGo",
        "primary": "#001b94",
        "accent": "#00a8e8",
        "services": "NUSW, WEBC",
        "meal": "6E Eats Choice Of The Day (Non-veg) + Beverage of choice, Web Checkin T & C Apply",
        "baggage": "15 kg Check-in · 7 kg Cabin",
    },
    "AI": {
        "name": "Air India",
        "primary": "#9A0002",
        "accent": "#D4AF37",
        "services": "VGML, WEBC",
        "meal": "Complimentary Maharaja Hot Meals + Beverage of choice, Web Checkin T & C Apply",
        "baggage": "20 kg Check-in · 7 kg Cabin",
    },
    "UK": {
        "name": "Vistara",
        "primary": "#4B1736",
        "accent": "#946E3A",
        "services": "AVML, WEBC",
        "meal": "Fly higher with Vistara Gourmet Dining + Signature Beverage, Web Checkin T & C Apply",
        "baggage": "15 kg Check-in · 7 kg Cabin",
    },
    "QP": {
        "name": "Akasa Air",
        "primary": "#E64A19",
        "accent": "#3B1C52",
        "services": "CKAS, WEBC",
        "meal": "Café Akasa Multi-cuisine Delights, Web Checkin T & C Apply",
        "baggage": "15 kg Check-in · 7 kg Cabin",
    },
    "SG": {
        "name": "SpiceJet",
        "primary": "#DE1A22",
        "accent": "#F9A01B",
        "services": "SPML, WEBC",
        "meal": "SpiceMax Special Meals & Refreshing Beverage, Web Checkin T & C Apply",
        "baggage": "15 kg Check-in · 7 kg Cabin",
    },
    "IX": {
        "name": "Air India Express",
        "primary": "#E64010",
        "accent": "#1565C0",
        "services": "GORM, WEBC",
        "meal": "Gourmair Fresh Meals & Beverage of choice, Web Checkin T & C Apply",
        "baggage": "15 kg Check-in · 7 kg Cabin",
    },
    "EK": {
        "name": "Emirates",
        "primary": "#D71921",
        "accent": "#CBA052",
        "services": "INFL, WEBC",
        "meal": "Emirates Multi-course Dining & Ice Entertainment, Web Checkin T & C Apply",
        "baggage": "25 kg Check-in · 7 kg Cabin",
    },
    "QR": {
        "name": "Qatar Airways",
        "primary": "#5C0632",
        "accent": "#B89D5B",
        "services": "WINE, WEBC",
        "meal": "World's Best Airline In-Flight Cuisine, Web Checkin T & C Apply",
        "baggage": "25 kg Check-in · 7 kg Cabin",
    },
    "SQ": {
        "name": "Singapore Airlines",
        "primary": "#1D3762",
        "accent": "#C89D42",
        "services": "SKML, WEBC",
        "meal": "A Great Way to Fly — Signature In-Flight Dining, Web Checkin T & C Apply",
        "baggage": "25 kg Check-in · 7 kg Cabin",
    },
    "BA": {
        "name": "British Airways",
        "primary": "#075AAA",
        "accent": "#EB2226",
        "services": "BAFD, WEBC",
        "meal": "Club World Hospitality & British Dining, Web Checkin T & C Apply",
        "baggage": "23 kg Check-in · 7 kg Cabin",
    },
    "LH": {
        "name": "Lufthansa",
        "primary": "#05164D",
        "accent": "#FFAC00",
        "services": "LHML, WEBC",
        "meal": "Say Yes to the World — German Hospitality, Web Checkin T & C Apply",
        "baggage": "23 kg Check-in · 8 kg Cabin",
    },
    "DL": {
        "name": "Delta Air Lines",
        "primary": "#002855",
        "accent": "#E51937",
        "services": "DLFD, WEBC",
        "meal": "Delta Sky Priority Hospitality & Refreshments, Web Checkin T & C Apply",
        "baggage": "23 kg Check-in · 7 kg Cabin",
    },
    "UA": {
        "name": "United Airlines",
        "primary": "#002244",
        "accent": "#005DAA",
        "services": "UAFD, WEBC",
        "meal": "United In-Flight Dining & Premium Refreshments, Web Checkin T & C Apply",
        "baggage": "23 kg Check-in · 7 kg Cabin",
    },
    "AA": {
        "name": "American Airlines",
        "primary": "#002244",
        "accent": "#C8102E",
        "services": "AAFD, WEBC",
        "meal": "American Airlines Main Cabin Hospitality, Web Checkin T & C Apply",
        "baggage": "23 kg Check-in · 7 kg Cabin",
    },
    "AF": {
        "name": "Air France",
        "primary": "#002157",
        "accent": "#ED0000",
        "services": "AFFD, WEBC",
        "meal": "Air France French Gastronomy Experience, Web Checkin T & C Apply",
        "baggage": "23 kg Check-in · 12 kg Cabin",
    },
    "9I": {
        "name": "Alliance Air",
        "primary": "#003366",
        "accent": "#FF6600",
        "services": "ALNC, WEBC",
        "meal": "Alliance Air Fresh Light Refreshments & Bottled Water, Web Checkin T & C Apply",
        "baggage": "15 kg Check-in · 7 kg Cabin",
    },
    "S5": {
        "name": "Star Air",
        "primary": "#8B0000",
        "accent": "#FFC107",
        "services": "STAR, WEBC",
        "meal": "Star Comfort Snack Box & Refreshing Beverages, Web Checkin T & C Apply",
        "baggage": "15 kg Check-in · 7 kg Cabin",
    },
    "IC": {
        "name": "Fly91",
        "primary": "#0284C7",
        "accent": "#F59E0B",
        "services": "FL91, WEBC",
        "meal": "Fly91 Goan Hospitality Refreshments & Snacks, Web Checkin T & C Apply",
        "baggage": "15 kg Check-in · 7 kg Cabin",
    },
    "I7": {
        "name": "IndiaOne Air",
        "primary": "#D9531E",
        "accent": "#1E3A8A",
        "services": "IOAR, WEBC",
        "meal": "IndiaOne Air Regional Refreshment Pack, Web Checkin T & C Apply",
        "baggage": "10 kg Check-in · 5 kg Cabin",
    },
    "EY": {
        "name": "Etihad Airways",
        "primary": "#BD8B22",
        "accent": "#231F20",
        "services": "EYFD, WEBC",
        "meal": "Etihad Contemporary Fine Dining & Beverage of choice, Web Checkin T & C Apply",
        "baggage": "25 kg Check-in · 7 kg Cabin",
    },
    "G9": {
        "name": "Air Arabia",
        "primary": "#E21836",
        "accent": "#4A4A4A",
        "services": "G9FD, WEBC",
        "meal": "Air Arabia Sky Café Refreshments & Snacks, Web Checkin T & C Apply",
        "baggage": "20 kg Check-in · 7 kg Cabin",
    },
    "GF": {
        "name": "Gulf Air",
        "primary": "#A68644",
        "accent": "#1A1A1A",
        "services": "GFFD, WEBC",
        "meal": "Gulf Air Arabian Hospitality Dining & Refreshments, Web Checkin T & C Apply",
        "baggage": "23 kg Check-in · 7 kg Cabin",
    },
    "FZ": {
        "name": "flydubai",
        "primary": "#006699",
        "accent": "#F26522",
        "services": "FZFD, WEBC",
        "meal": "flydubai Fresh In-Flight Meals & Beverages, Web Checkin T & C Apply",
        "baggage": "20 kg Check-in · 7 kg Cabin",
    },
    "SV": {
        "name": "Saudia",
        "primary": "#006C35",
        "accent": "#A28C5B",
        "services": "SVFD, WEBC",
        "meal": "Saudia Traditional Arabic & World Dining, Web Checkin T & C Apply",
        "baggage": "25 kg Check-in · 7 kg Cabin",
    },
    "WY": {
        "name": "Oman Air",
        "primary": "#C4262E",
        "accent": "#1E3A8A",
        "services": "WYFD, WEBC",
        "meal": "Oman Air Signature Omani Dining & Refreshments, Web Checkin T & C Apply",
        "baggage": "25 kg Check-in · 7 kg Cabin",
    },
    "MH": {
        "name": "Malaysia Airlines",
        "primary": "#0F2A66",
        "accent": "#E51B24",
        "services": "MHFD, WEBC",
        "meal": "Malaysian Hospitality In-Flight Signature Dining, Web Checkin T & C Apply",
        "baggage": "25 kg Check-in · 7 kg Cabin",
    },
    "TG": {
        "name": "Thai Airways",
        "primary": "#4B2882",
        "accent": "#DEB841",
        "services": "TGFD, WEBC",
        "meal": "Smooth as Silk Royal Orchid Cuisine, Web Checkin T & C Apply",
        "baggage": "25 kg Check-in · 7 kg Cabin",
    },
    "CX": {
        "name": "Cathay Pacific",
        "primary": "#006564",
        "accent": "#C8102E",
        "services": "CXFD, WEBC",
        "meal": "Cathay Pacific Curated World Flavours & Beverage, Web Checkin T & C Apply",
        "baggage": "25 kg Check-in · 7 kg Cabin",
    },
    "JL": {
        "name": "Japan Airlines",
        "primary": "#C8102E",
        "accent": "#231F20",
        "services": "JLFD, WEBC",
        "meal": "JAL Omotenashi Japanese & International Cuisine, Web Checkin T & C Apply",
        "baggage": "23 kg Check-in (2 pcs) · 10 kg Cabin",
    },
    "VN": {
        "name": "Vietnam Airlines",
        "primary": "#005574",
        "accent": "#E2AA29",
        "services": "VNFD, WEBC",
        "meal": "Vietnam Airlines Lotus Gourmet Dining & Pho, Web Checkin T & C Apply",
        "baggage": "23 kg Check-in · 12 kg Cabin",
    },
    "KL": {
        "name": "KLM",
        "primary": "#00A1DE",
        "accent": "#1A365D",
        "services": "KLFD, WEBC",
        "meal": "KLM Royal Dutch Hospitality & European Dining, Web Checkin T & C Apply",
        "baggage": "23 kg Check-in · 12 kg Cabin",
    },
    "VS": {
        "name": "Virgin Atlantic",
        "primary": "#E10A11",
        "accent": "#4C1234",
        "services": "VSFD, WEBC",
        "meal": "Virgin Atlantic Celebrated In-Flight Dining Experience, Web Checkin T & C Apply",
        "baggage": "23 kg Check-in · 10 kg Cabin",
    },
    "LX": {
        "name": "Swiss International Air Lines",
        "primary": "#E30613",
        "accent": "#1F2937",
        "services": "LXFD, WEBC",
        "meal": "Swiss Taste of Switzerland Gourmet Dining & Chocolates, Web Checkin T & C Apply",
        "baggage": "23 kg Check-in · 8 kg Cabin",
    },
    "AC": {
        "name": "Air Canada",
        "primary": "#F01428",
        "accent": "#111827",
        "services": "ACFD, WEBC",
        "meal": "Air Canada Canadian Maple Dining & Refreshments, Web Checkin T & C Apply",
        "baggage": "23 kg Check-in (2 pcs) · 10 kg Cabin",
    },
    "UL": {
        "name": "SriLankan Airlines",
        "primary": "#0B2265",
        "accent": "#F37023",
        "services": "ULFD, WEBC",
        "meal": "SriLankan Island Hospitality Dining & Ceylon Tea, Web Checkin T & C Apply",
        "baggage": "25 kg Check-in · 7 kg Cabin",
    },
    "BG": {
        "name": "Biman Bangladesh Airlines",
        "primary": "#006A4E",
        "accent": "#F42A41",
        "services": "BGFD, WEBC",
        "meal": "Biman Traditional Bengali In-Flight Cuisine, Web Checkin T & C Apply",
        "baggage": "20 kg Check-in · 7 kg Cabin",
    },
    "KB": {
        "name": "Drukair",
        "primary": "#E65100",
        "accent": "#FFB300",
        "services": "KBFD, WEBC",
        "meal": "Drukair Royal Bhutan Hospitality & Mountain Refreshments, Web Checkin T & C Apply",
        "baggage": "20 kg Check-in · 7 kg Cabin",
    },
    "KU": {
        "name": "Kuwait Airways",
        "primary": "#004080",
        "accent": "#A3D4EB",
        "services": "KUFD, WEBC",
        "meal": "Kuwait Airways Oasis In-Flight Dining, Web Checkin T & C Apply",
        "baggage": "23 kg Check-in (2 pcs) · 7 kg Cabin",
    },
    "J9": {
        "name": "Jazeera Airways",
        "primary": "#002D62",
        "accent": "#F58220",
        "services": "J9FD, WEBC",
        "meal": "Jazeera Café Fresh Bites & Drinks, Web Checkin T & C Apply",
        "baggage": "20 kg Check-in · 7 kg Cabin",
    },
    "OV": {
        "name": "SalamAir",
        "primary": "#008080",
        "accent": "#8DC63F",
        "services": "OVFD, WEBC",
        "meal": "SalamAir Simply Omani In-Flight Hospitality, Web Checkin T & C Apply",
        "baggage": "20 kg Check-in · 7 kg Cabin",
    },
    "XY": {
        "name": "flynas",
        "primary": "#6C2D82",
        "accent": "#00A79D",
        "services": "XYFD, WEBC",
        "meal": "flynas Snack Selection & Refreshments, Web Checkin T & C Apply",
        "baggage": "20 kg Check-in · 7 kg Cabin",
    },
    "NH": {
        "name": "All Nippon Airways",
        "primary": "#003893",
        "accent": "#00A0E9",
        "services": "NHFD, WEBC",
        "meal": "ANA Inspiration of Japan Authentic Dining, Web Checkin T & C Apply",
        "baggage": "23 kg Check-in (2 pcs) · 10 kg Cabin",
    },
    "KE": {
        "name": "Korean Air",
        "primary": "#004B87",
        "accent": "#E60012",
        "services": "KEFD, WEBC",
        "meal": "Korean Air Bibimbap & World-Class In-Flight Dining, Web Checkin T & C Apply",
        "baggage": "23 kg Check-in (2 pcs) · 10 kg Cabin",
    },
    "OD": {
        "name": "Batik Air Malaysia",
        "primary": "#8B0000",
        "accent": "#FFD700",
        "services": "ODFD, WEBC",
        "meal": "Batik Air Malaysian Warm Meals & Beverages, Web Checkin T & C Apply",
        "baggage": "20 kg Check-in · 7 kg Cabin",
    },
    "GA": {
        "name": "Garuda Indonesia",
        "primary": "#004B87",
        "accent": "#5BB5C1",
        "services": "GAFD, WEBC",
        "meal": "Garuda Indonesia Indonesian Hospitality Dining, Web Checkin T & C Apply",
        "baggage": "30 kg Check-in · 7 kg Cabin",
    },
    "AY": {
        "name": "Finnair",
        "primary": "#0B1560",
        "accent": "#FFFFFF",
        "services": "AYFD, WEBC",
        "meal": "Finnair Nordic Gastronomy & Fresh Flavours, Web Checkin T & C Apply",
        "baggage": "23 kg Check-in · 8 kg Cabin",
    },
    "LO": {
        "name": "LOT Polish Airlines",
        "primary": "#0D2240",
        "accent": "#00508F",
        "services": "LOFD, WEBC",
        "meal": "LOT Traditional Polish & European Dining, Web Checkin T & C Apply",
        "baggage": "23 kg Check-in · 8 kg Cabin",
    },
    "AZ": {
        "name": "ITA Airways",
        "primary": "#003865",
        "accent": "#CE2B37",
        "services": "AZFD, WEBC",
        "meal": "ITA Airways Authentic Italian Cuisine & Espresso, Web Checkin T & C Apply",
        "baggage": "23 kg Check-in · 8 kg Cabin",
    },
    "TK": {
        "name": "Turkish Airlines",
        "primary": "#C8102E",
        "accent": "#231F20",
        "services": "TKFD, WEBC",
        "meal": "Turkish Airlines Flying Chefs Dining Experience, Web Checkin T & C Apply",
        "baggage": "25 kg Check-in · 8 kg Cabin",
    },
    "ET": {
        "name": "Ethiopian Airlines",
        "primary": "#00843D",
        "accent": "#EF3340",
        "services": "ETFD, WEBC",
        "meal": "Ethiopian Airlines National In-Flight Cuisine, Web Checkin T & C Apply",
        "baggage": "23 kg Check-in (2 pcs) · 7 kg Cabin",
    },
    "MS": {
        "name": "EgyptAir",
        "primary": "#0A2240",
        "accent": "#D4AF37",
        "services": "MSFD, WEBC",
        "meal": "EgyptAir Mediterranean Hospitality & Dining, Web Checkin T & C Apply",
        "baggage": "23 kg Check-in (2 pcs) · 7 kg Cabin",
    },
    "KQ": {
        "name": "Kenya Airways",
        "primary": "#BD1622",
        "accent": "#1A1A1A",
        "services": "KQFD, WEBC",
        "meal": "Kenya Airways Pride of Africa Dining, Web Checkin T & C Apply",
        "baggage": "23 kg Check-in (2 pcs) · 7 kg Cabin",
    },
    "MK": {
        "name": "Air Mauritius",
        "primary": "#ED1C24",
        "accent": "#003865",
        "services": "MKFD, WEBC",
        "meal": "Air Mauritius Creole Gourmet Dining, Web Checkin T & C Apply",
        "baggage": "23 kg Check-in (2 pcs) · 7 kg Cabin",
    },
    "QF": {
        "name": "Qantas",
        "primary": "#E0001B",
        "accent": "#222222",
        "services": "QFFD, WEBC",
        "meal": "Qantas Australian Produce Dining by Neil Perry, Web Checkin T & C Apply",
        "baggage": "30 kg Check-in · 7 kg Cabin",
    },
    "RA": {
        "name": "Nepal Airlines",
        "primary": "#DC143C",
        "accent": "#003893",
        "services": "RAFD, WEBC",
        "meal": "Nepal Airlines Himalayan Hospitality & Meals, Web Checkin T & C Apply",
        "baggage": "25 kg Check-in · 7 kg Cabin",
    },
    "Q2": {
        "name": "Maldivian",
        "primary": "#008080",
        "accent": "#FFD700",
        "services": "Q2FD, WEBC",
        "meal": "Maldivian Island Refreshments & Beverages, Web Checkin T & C Apply",
        "baggage": "20 kg Check-in · 7 kg Cabin",
    },
}

# Lookup by airline name keywords
NAME_TO_CODE = {
    "indigo": "6E",
    "air india express": "IX",
    "air india": "AI",
    "vistara": "UK",
    "akasa": "QP",
    "spicejet": "SG",
    "alliance air": "9I",
    "star air": "S5",
    "fly91": "IC",
    "indiaone air": "I7",
    "indiaone": "I7",
    "emirates": "EK",
    "qatar": "QR",
    "singapore": "SQ",
    "etihad": "EY",
    "air arabia": "G9",
    "gulf air": "GF",
    "flydubai": "FZ",
    "saudia": "SV",
    "saudi": "SV",
    "oman air": "WY",
    "malaysia airlines": "MH",
    "malaysia": "MH",
    "thai airways": "TG",
    "thai": "TG",
    "cathay pacific": "CX",
    "cathay": "CX",
    "japan airlines": "JL",
    "vietnam airlines": "VN",
    "vietnam": "VN",
    "british airways": "BA",
    "lufthansa": "LH",
    "delta": "DL",
    "united": "UA",
    "american airlines": "AA",
    "air france": "AF",
    "klm": "KL",
    "virgin atlantic": "VS",
    "swiss": "LX",
    "air canada": "AC",
    "srilankan": "UL",
    "sri lankan": "UL",
    "biman bangladesh": "BG",
    "biman": "BG",
    "drukair": "KB",
    "druk air": "KB",
    "kuwait": "KU",
    "jazeera": "J9",
    "salamair": "OV",
    "salam air": "OV",
    "flynas": "XY",
    "ana": "NH",
    "all nippon": "NH",
    "korean air": "KE",
    "batik air": "OD",
    "batik": "OD",
    "garuda": "GA",
    "finnair": "AY",
    "lot polish": "LO",
    "ita airways": "AZ",
    "turkish": "TK",
    "ethiopian": "ET",
    "egyptair": "MS",
    "kenya airways": "KQ",
    "mauritius": "MK",
    "qantas": "QF",
    "nepal airlines": "RA",
    "maldivian": "Q2",
}



def resolve_airline_profile(flight_number: str, airline_name: str = "") -> dict:
    """Find or dynamically construct the airline brand profile for any flight."""
    raw_flight = (flight_number or "").strip().upper()
    prefix = ""
    for char in raw_flight:
        if char.isdigit():
            break
        prefix += char
    prefix = prefix.strip()
    
    # Try exact prefix match
    if prefix in AIRLINE_REGISTRY:
        return {"code": prefix, **AIRLINE_REGISTRY[prefix]}
    
    # Try name match
    name_clean = (airline_name or "").strip().lower()
    for key, code in NAME_TO_CODE.items():
        if key in name_clean:
            return {"code": code, **AIRLINE_REGISTRY[code]}
            
    # Dynamic fallback for any other airline
    airline_display = airline_name or (prefix + " Airways" if prefix else "Airways")
    # Generate deterministic color from name
    h = hashlib.md5(airline_display.encode()).hexdigest()
    hue_primary = f"#{h[:6]}"
    hue_accent = f"#{h[6:12]}"
    
    # Ensure it's not too light for white text
    return {
        "code": prefix or "FL",
        "name": airline_display,
        "primary": "#0F223D",  # Sleek deep navy aviation default
        "accent": "#0284C7",
        "services": "NUSW, WEBC",
        "meal": f"{airline_display} In-Flight Hospitality, Web Checkin T & C Apply",
        "baggage": "15 kg Check-in · 7 kg Cabin",
    }


def format_booking_date(date_val, fmt: str = "%d %b %Y") -> str:
    """Safely formats a date object or ISO date string."""
    if not date_val:
        return ""
    if hasattr(date_val, "strftime"):
        return date_val.strftime(fmt)
    try:
        from datetime import date
        return date.fromisoformat(str(date_val)[:10]).strftime(fmt)
    except Exception:
        return str(date_val)


def generate_qr_data_uri(payload: str, box_size: int = 4) -> str:
    """Generates an embedded PNG data URI for offline QR code rendering."""
    try:
        qr = qrcode.QRCode(version=1, box_size=box_size, border=0)
        qr.add_data(payload)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        return f"data:image/png;base64,{b64}"
    except Exception as e:
        logger.warning("Failed to generate QR data URI: %s", e)
        return ""


def draw_airline_logo(c: canvas.Canvas, code: str, name: str, x: float, y: float) -> None:
    """Renders authentic vector brand logo and typography on the banner."""
    c.saveState()
    c.setFillColor(colors.white)
    
    code_up = code.upper()
    if code_up == "6E":
        c.setFont("Helvetica-Bold", 18)
        c.drawString(x, y, "IndiGo")
        # Tail dots pattern
        dot_x = x + 68
        for row in range(3):
            for col in range(3):
                if row + col >= 2:
                    c.circle(dot_x + col * 4, y + row * 4, 1.3, stroke=0, fill=1)
        sub_x = x + 95
    elif code_up == "AI":
        c.setFont("Helvetica-Bold", 18)
        c.drawString(x + 22, y, "AIR INDIA")
        # Flying swan crest
        c.setStrokeColor(HexColor("#D4AF37"))
        c.setLineWidth(1.6)
        c.arc(x, y - 2, x + 18, y + 16, 45, 270)
        c.circle(x + 8, y + 10, 2, stroke=0, fill=1)
        sub_x = x + 130
    elif code_up == "UK":
        c.setFont("Helvetica-Bold", 18)
        c.drawString(x + 22, y, "VISTARA")
        # Star emblem
        c.setFillColor(HexColor("#D4AF37"))
        c.circle(x + 9, y + 6, 6, stroke=0, fill=1)
        c.setFillColor(colors.white)
        sub_x = x + 118
    elif code_up == "QP":
        c.setFont("Helvetica-Bold", 18)
        c.drawString(x + 22, y, "Akasa Air")
        # Rising A wing
        c.setStrokeColor(colors.white)
        c.setLineWidth(2.2)
        p = c.beginPath()
        p.moveTo(x, y + 1)
        p.lineTo(x + 9, y + 15)
        p.lineTo(x + 18, y + 1)
        c.drawPath(p, stroke=1, fill=0)
        sub_x = x + 120
    elif code_up == "SG":
        c.setFont("Helvetica-Bold", 18)
        c.drawString(x, y, "SpiceJet")
        dot_x = x + 82
        for r in range(3):
            for col in range(4):
                c.circle(dot_x + col * 3.5, y + r * 3.5, 1.1, stroke=0, fill=1)
        sub_x = x + 110
    elif code_up == "IX":
        c.setFont("Helvetica-Bold", 17)
        c.drawString(x + 18, y, "Air India Express")
        c.setStrokeColor(HexColor("#1565C0"))
        c.setLineWidth(2)
        c.line(x, y + 2, x + 12, y + 14)
        sub_x = x + 172
    elif code_up == "EK":
        c.setFont("Helvetica-Bold", 18)
        c.drawString(x + 20, y, "Emirates")
        c.setStrokeColor(HexColor("#CBA052"))
        c.setLineWidth(2)
        c.rect(x, y - 1, 14, 15, stroke=1, fill=0)
        sub_x = x + 115
    elif code_up == "QR":
        c.setFont("Helvetica-Bold", 18)
        c.drawString(x + 20, y, "Qatar Airways")
        c.setStrokeColor(HexColor("#B89D5B"))
        c.setLineWidth(1.6)
        c.circle(x + 7, y + 6, 7, stroke=1, fill=0)
        sub_x = x + 160
    elif code_up == "SQ":
        c.setFont("Helvetica-Bold", 18)
        c.drawString(x + 20, y, "Singapore Airlines")
        c.setFillColor(HexColor("#C89D42"))
        c.circle(x + 7, y + 6, 6, stroke=0, fill=1)
        c.setFillColor(colors.white)
        sub_x = x + 188
    else:
        c.setFont("Helvetica-Bold", 17)
        c.drawString(x + 22, y, name)
        c.setFont("Helvetica", 16)
        c.drawString(x, y - 1, "✈")
        sub_x = x + 28 + len(name) * 9.2
        
    c.setFont("Helvetica-Bold", 12.5)
    c.drawString(sub_x, y + 1, "Boarding Pass (Web Check-In)")
    c.restoreState()


def render_passenger_page(
    c: canvas.Canvas,
    booking,
    passenger,
    pax_index: int,
    cfg: dict,
    total_passengers: int,
) -> None:
    """Renders a single boarding pass coupon page matching the authentic airline boarding pass design."""
    width = 840
    height = 400
    
    primary_color = HexColor(cfg["primary"])
    bg_light = HexColor("#ffffff")
    text_dark = HexColor("#111827")
    text_muted = HexColor("#4b5563")
    
    card_x = 20
    card_y = 35
    card_w = 800
    card_h = 340
    radius = 12
    
    # Outer card
    c.saveState()
    c.setFillColor(bg_light)
    c.setStrokeColor(primary_color)
    c.setLineWidth(1.5)
    c.roundRect(card_x, card_y, card_w, card_h, radius, stroke=1, fill=1)
    c.restoreState()
    
    # Top banner
    banner_h = 52
    banner_y = card_y + card_h - banner_h
    stub_w = 220
    split_x = card_x + card_w - stub_w
    
    # Draw clipped banner
    c.saveState()
    p = c.beginPath()
    p.roundRect(card_x, card_y, card_w, card_h, radius)
    c.clipPath(p, stroke=0)
    
    c.setFillColor(primary_color)
    c.rect(card_x, banner_y, card_w, banner_h, stroke=0, fill=1)
    
    # Brand logo & title
    draw_airline_logo(c, cfg["code"], cfg["name"], card_x + 18, banner_y + 18)
    
    # Right banner departure terminal and class text
    raw_dep_term = str(booking.dep_terminal or "1").strip()
    dep_term_num = raw_dep_term.lstrip("Tt").strip() or "1"
    dep_term = f"T{dep_term_num}"

    raw_travel_class = getattr(booking, "travel_class", "") or "Economy"
    travel_class = raw_travel_class.strip().title() if isinstance(raw_travel_class, str) else "Economy"
    is_connecting = bool(getattr(booking, "is_connecting", False))
    stops_info = getattr(booking, "stops_info", "") or ""
    
    term_text = f"{travel_class}  ·  Terminal {dep_term_num}"
    
    c.setFont("Helvetica-Bold", 10.5)
    c.setFillColor(colors.white)
    c.drawRightString(card_x + card_w - 42, banner_y + 20, term_text)
    c.setFont("Helvetica", 14)
    c.drawString(card_x + card_w - 32, banner_y + 19, "✈")
    c.restoreState()
    
    # Vertical perforation line
    c.saveState()
    c.setLineWidth(1.2)
    c.setStrokeColor(colors.white)
    c.setDash(4, 4)
    c.line(split_x, banner_y, split_x, card_y + card_h)
    c.setStrokeColor(primary_color)
    c.setDash(4, 4)
    c.line(split_x, card_y, split_x, banner_y)
    c.restoreState()
    
    # ---------------- LEFT MAIN PASS ----------------
    main_margin_left = card_x + 20
    content_y = banner_y - 25
    
    # Passenger Name & Route
    pax_name = passenger.formatted_name
    c.setFont("Helvetica-Bold", 12)
    c.setFillColor(text_dark)
    c.drawString(main_margin_left, content_y, pax_name)
    
    # Terminal formatting for route
    src_term_label = f" ({dep_term})" if dep_term else ""
    snapshot = booking.snapshot if isinstance(getattr(booking, "snapshot", None), dict) else {}
    raw_arr_term = str(snapshot.get("arr_terminal") or "2").strip()
    arr_term_num = raw_arr_term.lstrip("Tt").strip() or "2"
    arr_term = f"T{arr_term_num}"
    dst_term_label = f" ({arr_term})" if arr_term else ""
    
    src_raw = (booking.dep_airport or booking.dep_iata or "DEP").strip()
    src_city = (src_raw.split()[0] if src_raw.split() else "DEP").upper()
    dst_raw = (booking.arr_airport or booking.arr_iata or "ARR").strip()
    dst_city = (dst_raw.split()[0] if dst_raw.split() else "ARR").upper()
    if is_connecting:
        via_lbl = f" via {stops_info}" if stops_info else " (Connecting)"
        route_str = f"{src_city}{src_term_label}  To  {dst_city}{dst_term_label}{via_lbl}"
    else:
        route_str = f"{src_city}{src_term_label}  To  {dst_city}{dst_term_label} (Non-stop)"
    
    c.setFont("Helvetica-Bold", 10.5)
    c.drawRightString(split_x - 20, content_y, route_str)
    
    # 5 Boxes row
    box_y = content_y - 82
    box_h = 68
    box_gap = 12
    box_w = (split_x - main_margin_left - 20 - (4 * box_gap)) / 5
    
    # Boarding time calculation: 45 minutes prior to scheduled departure
    sched_dep = booking.scheduled_departure
    if sched_dep and isinstance(sched_dep, str):
        try:
            sched_dep = datetime.fromisoformat(sched_dep)
        except Exception:
            sched_dep = None
    if sched_dep:
        local_dep = timezone.localtime(sched_dep) if (hasattr(timezone, "is_aware") and timezone.is_aware(sched_dep)) else sched_dep
        boarding_dt = local_dep - timedelta(minutes=45)
        boarding_time_str = boarding_dt.strftime("%H:%M hrs")
        dep_time_str = local_dep.strftime("%H:%M")
    else:
        boarding_time_str = "07:45 hrs"
        dep_time_str = "08:30"
        
    gate_display = str(booking.dep_gate or "—").strip()
    seat_display = passenger.seat_number or f"{8 + pax_index}{['A','B','C','D','E','F'][pax_index % 6]}"
    zone_display = passenger.boarding_zone or f"Zone {1 if pax_index == 0 else 3}"
    seq_display = passenger.sequence_number or f"{(pax_index + 1) * 26:04d}"
    
    boxes_data = [
        ("Flight", str(booking.flight_number or "—")),
        ("Gate", gate_display),
        ("Boarding Time", boarding_time_str),
        ("Boarding", zone_display),
        ("Seat", seat_display),
    ]
    
    for i, (lbl, val) in enumerate(boxes_data):
        bx = main_margin_left + i * (box_w + box_gap)
        c.saveState()
        c.setStrokeColor(primary_color)
        c.setLineWidth(1.2)
        c.roundRect(bx, box_y, box_w, box_h, 4, stroke=1, fill=0)
        
        # Label
        c.setFillColor(text_muted)
        c.setFont("Helvetica", 8.5)
        c.drawString(bx + 10, box_y + box_h - 16, lbl)
        
        # Value
        c.setFillColor(text_dark)
        font_size = 13.5 if len(val) > 7 else 15
        c.setFont("Helvetica-Bold", font_size)
        c.drawString(bx + 10, box_y + 18, val)
        c.restoreState()
        
    # QR Code generation (standard IATA BCBP payload)
    ref_str = (booking.reference or "").ljust(7)
    flt_str = (booking.flight_number or "").replace(" ", "")
    dep_iata = booking.dep_iata or ""
    arr_iata = booking.arr_iata or ""
    qr_payload = (
        f"M1{pax_name[:20].ljust(20)} E{ref_str} "
        f"{dep_iata}{arr_iata}{flt_str} "
        f"{seat_display.ljust(4)}{seq_display.ljust(4)}"
    )
    qr = qrcode.QRCode(version=1, box_size=4, border=0)
    qr.add_data(qr_payload)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white")
    qr_buffer = io.BytesIO()
    qr_img.save(qr_buffer, format="PNG")
    qr_buffer.seek(0)
    
    qr_size = 80
    qr_x = main_margin_left + 5
    qr_y = box_y - qr_size - 18
    
    img_reader = ImageReader(qr_buffer)
    c.drawImage(img_reader, qr_x, qr_y, width=qr_size, height=qr_size)
    
    # Flight meta table beside QR code
    meta_x1 = qr_x + qr_size + 24
    meta_x2 = meta_x1 + 130
    date_formatted = format_booking_date(booking.dep_date)
    
    c.setFont("Helvetica", 9.5)
    c.setFillColor(text_muted)
    c.drawString(meta_x1, qr_y + 55, "Date")
    c.setFont("Helvetica-Bold", 10.5)
    c.setFillColor(text_dark)
    c.drawString(meta_x1 + 35, qr_y + 55, date_formatted)
    
    c.setFont("Helvetica", 9.5)
    c.setFillColor(text_muted)
    c.drawString(meta_x1, qr_y + 32, "Class")
    c.setFont("Helvetica-Bold", 10.5)
    c.setFillColor(text_dark)
    c.drawString(meta_x1 + 35, qr_y + 32, travel_class)
    
    c.setFont("Helvetica", 9.5)
    c.setFillColor(text_muted)
    c.drawString(meta_x2, qr_y + 55, "Departure")
    c.setFont("Helvetica-Bold", 10.5)
    c.setFillColor(text_dark)
    c.drawString(meta_x2 + 65, qr_y + 55, dep_time_str)
    
    c.setFont("Helvetica", 9.5)
    c.setFillColor(text_muted)
    c.drawString(meta_x2, qr_y + 32, "Routing")
    c.setFont("Helvetica-Bold", 10.5)
    c.setFillColor(text_dark)
    c.drawString(meta_x2 + 65, qr_y + 32, f"Via {stops_info}" if is_connecting else "Non-stop")
    
    # Gate notice
    c.setFont("Helvetica", 8.5)
    c.setFillColor(text_muted)
    c.drawString(meta_x1, qr_y + 6, "Gate closes 25 mins prior to departure · Valid photo ID / Passport required")
    
    # ---------------- RIGHT STUB ----------------
    stub_left = split_x + 18
    stub_content_y = banner_y - 25
    
    c.setFont("Helvetica-Bold", 10.5)
    c.setFillColor(text_dark)
    name_parts = pax_name.split("/")
    if len(name_parts) >= 2:
        c.drawString(stub_left, stub_content_y, name_parts[0])
        c.drawString(stub_left, stub_content_y - 13, "/".join(name_parts[1:]))
    else:
        c.drawString(stub_left, stub_content_y, pax_name)
        
    c.setFont("Helvetica-Bold", 8.5)
    stub_dest = f"{dst_city[:3]}{dst_term_label}"
    if is_connecting and stops_info:
        stub_dest += f" (via {stops_info})"
    c.drawString(stub_left, stub_content_y - 28, f"{src_city}{src_term_label}  To  {stub_dest}")
    
    stub_kv = [
        ("PNR", str(booking.reference or "—")),
        ("Flight", str(booking.flight_number or "—")),
        ("Class", str(travel_class)),
        ("Date", date_formatted),
    ]
    
    kv_y = stub_content_y - 56
    for lbl, val in stub_kv:
        c.setFont("Helvetica", 9)
        c.setFillColor(text_muted)
        c.drawString(stub_left, kv_y, lbl)
        c.setFont("Helvetica-Bold", 9)
        c.setFillColor(text_dark)
        c.drawRightString(card_x + card_w - 20, kv_y, val)
        kv_y -= 15
        
    # Small QR in stub
    small_qr_size = 50
    small_qr_y = card_y + 22
    small_qr_x = stub_left
    c.drawImage(img_reader, small_qr_x, small_qr_y, width=small_qr_size, height=small_qr_size)
    
    seat_seq_x = small_qr_x + small_qr_size + 15
    c.setFont("Helvetica", 9.5)
    c.setFillColor(text_muted)
    c.drawString(seat_seq_x, small_qr_y + 30, "Seat")
    c.setFont("Helvetica-Bold", 12)
    c.setFillColor(text_dark)
    c.drawString(seat_seq_x + 36, small_qr_y + 30, seat_display)
    
    c.setFont("Helvetica", 9.5)
    c.setFillColor(text_muted)
    c.drawString(seat_seq_x, small_qr_y + 10, "Seq")
    c.setFont("Helvetica-Bold", 10.5)
    c.setFillColor(text_dark)
    c.drawString(seat_seq_x + 36, small_qr_y + 10, seq_display)
    
    # ---------------- FOOTER OUTSIDE CARD ----------------
    c.setFont("Helvetica", 8)
    c.setFillColor(text_dark)
    travel_class_lower = travel_class.lower()
    if "business" in travel_class_lower or "first" in travel_class_lower:
        footer_info = f"Priority SkyPriority & Lounge Access Included · Baggage 35 kg Check-in · 10 kg Cabin · {cfg['meal']}"
    elif "premium" in travel_class_lower:
        footer_info = f"Premium Hospitality & Extra Legroom · Baggage 25 kg Check-in · 8 kg Cabin · {cfg['meal']}"
    else:
        footer_info = f"Baggage: {cfg['baggage']} · {cfg['meal']}"
    c.drawString(card_x, card_y - 16, footer_info)
    
    c.showPage()


def generate_boarding_passes_pdf(booking) -> io.BytesIO:
    """Generates a complete multi-passenger PDF containing high-resolution boarding pass coupons."""
    cfg = resolve_airline_profile(booking.flight_number, booking.airline_name)
    passengers = list(booking.passengers.all()) if hasattr(booking.passengers, "all") else list(booking.passengers)
    
    # If no passengers saved, create a fallback single passenger representation
    if not passengers:
        from flights.models import Passenger
        first_name = "PRIMARY"
        last_name = "PASSENGER"
        if hasattr(booking, "user") and booking.user:
            first_name = getattr(booking.user, "first_name", "") or "PRIMARY"
            last_name = getattr(booking.user, "last_name", "") or "PASSENGER"
        passengers = [Passenger(
            first_name=first_name,
            last_name=last_name,
            gender="M",
            seat_number="8A",
            boarding_zone="Zone 3",
            sequence_number="0026",
        )]
        
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=(840, 400))
    c.setTitle(f"Boarding Pass - {booking.reference} - {cfg['name']}")
    c.setAuthor(cfg["name"])
    c.setSubject(f"Flight {booking.flight_number} Boarding Pass")
    
    for idx, pax in enumerate(passengers):
        # Auto-assign seat/zone/seq if missing
        if not pax.seat_number:
            pax.seat_number = f"{8 + idx}{['A','B','C','D','E','F'][idx % 6]}"
        if not pax.boarding_zone:
            pax.boarding_zone = f"Zone {1 if idx == 0 else 3}"
        if not pax.sequence_number:
            pax.sequence_number = f"{(idx + 1) * 26:04d}"
            
        render_passenger_page(c, booking, pax, idx, cfg, len(passengers))
        
    c.save()
    buffer.seek(0)
    return buffer


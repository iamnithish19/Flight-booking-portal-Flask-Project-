"""Static airport reference list (code <-> city <-> country) used for search autocomplete and routing.
Includes comprehensive coverage of ALL commercial Indian airports and major global hubs.
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

# Format: (IATA, City, Full Airport Name, Country Code, Country Name)
AIRPORTS_DATA: List[Tuple[str, str, str, str, str]] = [
    # ---- ALL INDIAN COMMERCIAL & REGIONAL AIRPORTS ----
    ("DEL", "Delhi", "Indira Gandhi International", "IN", "India"),
    ("BOM", "Mumbai", "Chhatrapati Shivaji Maharaj International", "IN", "India"),
    ("BLR", "Bengaluru", "Kempegowda International", "IN", "India"),
    ("MAA", "Chennai", "Chennai International", "IN", "India"),
    ("HYD", "Hyderabad", "Rajiv Gandhi International", "IN", "India"),
    ("CCU", "Kolkata", "Netaji Subhas Chandra Bose International", "IN", "India"),
    ("COK", "Kochi", "Cochin International", "IN", "India"),
    ("AMD", "Ahmedabad", "Sardar Vallabhbhai Patel International", "IN", "India"),
    ("PNQ", "Pune", "Pune Airport", "IN", "India"),
    ("GOI", "Goa (Dabolim)", "Dabolim Airport", "IN", "India"),
    ("GOX", "Goa (Mopa)", "Manohar International Airport", "IN", "India"),
    ("TRV", "Thiruvananthapuram", "Trivandrum International", "IN", "India"),
    ("CJB", "Coimbatore", "Coimbatore International", "IN", "India"),
    ("IXM", "Madurai", "Madurai Airport", "IN", "India"),
    ("TRZ", "Tiruchirappalli", "Tiruchirappalli International", "IN", "India"),
    ("TCR", "Thoothukudi", "Tuticorin Airport", "IN", "India"),
    ("SXV", "Salem", "Salem Airport", "IN", "India"),
    ("JAI", "Jaipur", "Jaipur International", "IN", "India"),
    ("LKO", "Lucknow", "Chaudhary Charan Singh International", "IN", "India"),
    ("PAT", "Patna", "Jay Prakash Narayan International", "IN", "India"),
    ("GAU", "Guwahati", "Lokpriya Gopinath Bordoloi International", "IN", "India"),
    ("IXC", "Chandigarh", "Chandigarh International", "IN", "India"),
    ("VNS", "Varanasi", "Lal Bahadur Shastri International", "IN", "India"),
    ("SXR", "Srinagar", "Sheikh ul-Alam International", "IN", "India"),
    ("IXZ", "Port Blair", "Veer Savarkar International", "IN", "India"),
    ("IXB", "Siliguri / Bagdogra", "Bagdogra Airport", "IN", "India"),
    ("BBI", "Bhubaneswar", "Biju Patnaik International", "IN", "India"),
    ("IXR", "Ranchi", "Birsa Munda Airport", "IN", "India"),
    ("IDR", "Indore", "Devi Ahilya Bai Holkar Airport", "IN", "India"),
    ("BHO", "Bhopal", "Raja Bhoj Airport", "IN", "India"),
    ("NAG", "Nagpur", "Dr. Babasaheb Ambedkar International", "IN", "India"),
    ("RPR", "Raipur", "Swami Vivekananda Airport", "IN", "India"),
    ("ATQ", "Amritsar", "Sri Guru Ram Dass Jee International", "IN", "India"),
    ("UDR", "Udaipur", "Maharana Pratap Airport", "IN", "India"),
    ("JDH", "Jodhpur", "Jodhpur Airport", "IN", "India"),
    ("DED", "Dehradun", "Jolly Grant Airport", "IN", "India"),
    ("IXJ", "Jammu", "Jammu Airport", "IN", "India"),
    ("IXL", "Leh", "Kushok Bakula Rimpochee Airport", "IN", "India"),
    ("IXA", "Agartala", "Maharaja Bir Bikram Airport", "IN", "India"),
    ("IMF", "Imphal", "Bir Tikendrajit International", "IN", "India"),
    ("DMU", "Dimapur", "Dimapur Airport", "IN", "India"),
    ("SHL", "Shillong", "Shillong Airport", "IN", "India"),
    ("AJL", "Aizawl", "Lengpui Airport", "IN", "India"),
    ("DIB", "Dibrugarh", "Dibrugarh Airport", "IN", "India"),
    ("IXS", "Silchar", "Silchar Airport", "IN", "India"),
    ("GAY", "Gaya", "Gaya Airport", "IN", "India"),
    ("TIR", "Tirupati", "Tirupati Airport", "IN", "India"),
    ("VGA", "Vijayawada", "Vijayawada Airport", "IN", "India"),
    ("VTZ", "Visakhapatnam", "Visakhapatnam International", "IN", "India"),
    ("RJA", "Rajahmundry", "Rajahmundry Airport", "IN", "India"),
    ("HBX", "Hubballi", "Hubballi Airport", "IN", "India"),
    ("IXG", "Belagavi", "Belagavi Airport", "IN", "India"),
    ("MYQ", "Mysuru", "Mysore Airport", "IN", "India"),
    ("IXE", "Mangaluru", "Mangaluru International", "IN", "India"),
    ("CCJ", "Kozhikode", "Calicut International", "IN", "India"),
    ("CNN", "Kannur", "Kannur International", "IN", "India"),
    ("JRG", "Jharsuguda", "Veer Surendra Sai Airport", "IN", "India"),
    ("DBR", "Darbhanga", "Darbhanga Airport", "IN", "India"),
    ("AYJ", "Ayodhya", "Maharishi Valmiki International", "IN", "India"),
    ("GWL", "Gwalior", "Rajmata Vijaya Raje Scindia Airport", "IN", "India"),
    ("JLR", "Jabalpur", "Jabalpur Airport", "IN", "India"),
    ("BEK", "Bareilly", "Bareilly Airport", "IN", "India"),
    ("GOP", "Gorakhpur", "Gorakhpur Airport", "IN", "India"),
    ("IXD", "Prayagraj", "Prayagraj Airport", "IN", "India"),
    ("HDO", "Hindon (NCR)", "Hindon Airport", "IN", "India"),
    ("STV", "Surat", "Surat International", "IN", "India"),
    ("BDQ", "Vadodara", "Vadodara Airport", "IN", "India"),
    ("HSR", "Rajkot", "Rajkot International Airport", "IN", "India"),
    ("BHU", "Bhavnagar", "Bhavnagar Airport", "IN", "India"),
    ("JGA", "Jamnagar", "Jamnagar Airport", "IN", "India"),
    ("PBD", "Porbandar", "Porbandar Airport", "IN", "India"),
    ("KNU", "Kanpur", "Kanpur Airport", "IN", "India"),
    ("AGR", "Agra", "Agra Airport", "IN", "India"),
    ("DHM", "Dharamshala", "Kangra Airport", "IN", "India"),
    ("KUU", "Kullu", "Kullu–Manali Airport", "IN", "India"),
    ("PGH", "Pantnagar", "Pantnagar Airport", "IN", "India"),
    ("KLH", "Kolhapur", "Kolhapur Airport", "IN", "India"),
    ("NDC", "Nanded", "Nanded Airport", "IN", "India"),
    ("SAG", "Shirdi", "Shirdi Airport", "IN", "India"),
    ("JGB", "Jagdalpur", "Jagdalpur Airport", "IN", "India"),
    ("IXW", "Jamshedpur", "Sonari Airport", "IN", "India"),
    ("BUP", "Bathinda", "Bathinda Airport", "IN", "India"),
    ("TEZ", "Tezpur", "Tezpur Airport", "IN", "India"),
    ("RUP", "Rupsi", "Rupsi Airport", "IN", "India"),
    ("PAB", "Bilaspur", "Bilaspur Airport", "IN", "India"),
    ("HGI", "Itanagar", "Donyi Polo Airport", "IN", "India"),
    ("COH", "Cooch Behar", "Cooch Behar Airport", "IN", "India"),

    # ---- MAJOR INTERNATIONAL HUBS (ABROAD / OVERSEAS) ----
    ("DXB", "Dubai", "Dubai International", "AE", "United Arab Emirates"),
    ("AUH", "Abu Dhabi", "Zayed International", "AE", "United Arab Emirates"),
    ("SHJ", "Sharjah", "Sharjah International", "AE", "United Arab Emirates"),
    ("DOH", "Doha", "Hamad International", "QA", "Qatar"),
    ("SIN", "Singapore", "Singapore Changi", "SG", "Singapore"),
    ("KUL", "Kuala Lumpur", "Kuala Lumpur International", "MY", "Malaysia"),
    ("BKK", "Bangkok", "Suvarnabhumi", "TH", "Thailand"),
    ("DMK", "Bangkok (Don Mueang)", "Don Mueang International", "TH", "Thailand"),
    ("HKT", "Phuket", "Phuket International", "TH", "Thailand"),
    ("CMB", "Colombo", "Bandaranaike International", "LK", "Sri Lanka"),
    ("MLE", "Male", "Velana International", "MV", "Maldives"),
    ("HKG", "Hong Kong", "Hong Kong International", "HK", "Hong Kong"),
    ("LHR", "London (Heathrow)", "London Heathrow", "GB", "United Kingdom"),
    ("LGW", "London (Gatwick)", "London Gatwick", "GB", "United Kingdom"),
    ("MAN", "Manchester", "Manchester Airport", "GB", "United Kingdom"),
    ("CDG", "Paris", "Paris Charles de Gaulle", "FR", "France"),
    ("FRA", "Frankfurt", "Frankfurt Airport", "DE", "Germany"),
    ("MUC", "Munich", "Munich Airport", "DE", "Germany"),
    ("AMS", "Amsterdam", "Amsterdam Airport Schiphol", "NL", "Netherlands"),
    ("ZRH", "Zurich", "Zurich Airport", "CH", "Switzerland"),
    ("FCO", "Rome", "Leonardo da Vinci–Fiumicino", "IT", "Italy"),
    ("IST", "Istanbul", "Istanbul Airport", "TR", "Turkey"),
    ("JFK", "New York (JFK)", "John F. Kennedy International", "US", "United States"),
    ("EWR", "Newark", "Newark Liberty International", "US", "United States"),
    ("ORD", "Chicago", "O'Hare International", "US", "United States"),
    ("SFO", "San Francisco", "San Francisco International", "US", "United States"),
    ("LAX", "Los Angeles", "Los Angeles International", "US", "United States"),
    ("YYZ", "Toronto", "Toronto Pearson International", "CA", "Canada"),
    ("YVR", "Vancouver", "Vancouver International", "CA", "Canada"),
    ("SYD", "Sydney", "Sydney Kingsford Smith", "AU", "Australia"),
    ("MEL", "Melbourne", "Melbourne Airport", "AU", "Australia"),
    ("NRT", "Tokyo (Narita)", "Narita International", "JP", "Japan"),
    ("HND", "Tokyo (Haneda)", "Haneda Airport", "JP", "Japan"),
    ("ICN", "Seoul", "Incheon International", "KR", "South Korea"),
    ("KWI", "Kuwait City", "Kuwait International", "KW", "Kuwait"),
    ("BAH", "Manama", "Bahrain International", "BH", "Bahrain"),
    ("MCT", "Muscat", "Muscat International", "OM", "Oman"),
    ("RUH", "Riyadh", "King Khalid International", "SA", "Saudi Arabia"),
    ("JED", "Jeddah", "King Abdulaziz International", "SA", "Saudi Arabia"),
    ("KTM", "Kathmandu", "Tribhuvan International", "NP", "Nepal"),
    ("DAC", "Dhaka", "Hazrat Shahjalal International", "BD", "Bangladesh"),
    ("PBH", "Paro", "Paro International Airport", "BT", "Bhutan"),
    ("HAN", "Hanoi", "Noi Bai International Airport", "VN", "Vietnam"),
    ("SGN", "Ho Chi Minh City", "Tan Son Nhat International Airport", "VN", "Vietnam"),
    ("YUL", "Montreal", "Montréal–Trudeau International", "CA", "Canada"),
    ("CGK", "Jakarta", "Soekarno–Hatta International", "ID", "Indonesia"),
    ("DPS", "Bali (Denpasar)", "Ngurah Rai International", "ID", "Indonesia"),
    ("MNL", "Manila", "Ninoy Aquino International", "PH", "Philippines"),
    ("MRU", "Mauritius", "Sir Seewoosagur Ramgoolam International", "MU", "Mauritius"),
    ("CAI", "Cairo", "Cairo International", "EG", "Egypt"),
    ("ADD", "Addis Ababa", "Addis Ababa Bole International", "ET", "Ethiopia"),
    ("NBO", "Nairobi", "Jomo Kenyatta International", "KE", "Kenya"),
    ("HEL", "Helsinki", "Helsinki Airport", "FI", "Finland"),
    ("WAW", "Warsaw", "Warsaw Chopin Airport", "PL", "Poland"),
]

# Legacy tuple structure (code, city, name) for backwards compatibility
AIRPORTS: List[Tuple[str, str, str]] = [(item[0], item[1], item[2]) for item in AIRPORTS_DATA]
AIRPORT_REGISTRY: Dict[str, Tuple[str, str, str, str, str]] = {item[0].upper(): item for item in AIRPORTS_DATA}
_BY_CODE: Dict[str, Tuple[str, str, str, str, str]] = AIRPORT_REGISTRY
_CODE_RE = re.compile(r"\(([A-Za-z]{3})\)|^\s*([A-Za-z]{3})\s*$")


def label(code: str) -> str:
    """Returns 'City (IATA)' format for airport chips and displays."""
    entry = _BY_CODE.get((code or "").upper())
    if entry:
        return f"{entry[1]} ({entry[0]})"
    return (code or "").upper()


def airport_name(code: str) -> str:
    """Returns the descriptive airport name."""
    entry = _BY_CODE.get((code or "").upper())
    if entry:
        return entry[2]
    return (code or "").upper()


def get_airport_country(code: str) -> str:
    """Returns the 2-letter ISO country code (e.g., 'IN', 'AE', 'US')."""
    entry = _BY_CODE.get((code or "").upper())
    return entry[3] if entry else "IN"


def get_airport_country_name(code: str) -> str:
    """Returns the full country name."""
    entry = _BY_CODE.get((code or "").upper())
    return entry[4] if entry else "India"


def is_international_route(source_code: str, dest_code: str) -> bool:
    """Determines whether a flight route crosses international borders."""
    src_c = get_airport_country(source_code)
    dst_c = get_airport_country(dest_code)
    return src_c != dst_c or src_c != "IN"


def parse_code(text: str) -> Optional[str]:
    """'Chennai (MAA)' -> 'MAA', 'maa' -> 'MAA'; also resolves bare city names from the directory."""
    text = (text or "").strip()
    m = _CODE_RE.search(text)
    if m:
        return (m.group(1) or m.group(2)).upper()
    text_lower = text.lower()
    for code, city, full_name, _, _ in AIRPORTS_DATA:
        if city.lower() == text_lower or full_name.lower() == text_lower or code.lower() == text_lower:
            return code
    return None


# Comprehensive list of nationalities for traveler passport/country selection
NATIONALITY_CHOICES: List[Tuple[str, str]] = [
    ("India", "India"),
    ("United States", "United States"),
    ("United Arab Emirates", "United Arab Emirates"),
    ("United Kingdom", "United Kingdom"),
    ("Singapore", "Singapore"),
    ("Malaysia", "Malaysia"),
    ("Qatar", "Qatar"),
    ("Saudi Arabia", "Saudi Arabia"),
    ("Kuwait", "Kuwait"),
    ("Oman", "Oman"),
    ("Bahrain", "Bahrain"),
    ("Canada", "Canada"),
    ("Australia", "Australia"),
    ("Germany", "Germany"),
    ("France", "France"),
    ("Sri Lanka", "Sri Lanka"),
    ("Nepal", "Nepal"),
    ("Bangladesh", "Bangladesh"),
    ("Bhutan", "Bhutan"),
    ("Vietnam", "Vietnam"),
    ("Thailand", "Thailand"),
    ("Japan", "Japan"),
    ("South Korea", "South Korea"),
    ("China", "China"),
    ("Italy", "Italy"),
    ("Spain", "Spain"),
    ("Netherlands", "Netherlands"),
    ("Switzerland", "Switzerland"),
    ("Maldives", "Maldives"),
    ("Turkey", "Turkey"),
    ("Indonesia", "Indonesia"),
    ("Philippines", "Philippines"),
    ("Mauritius", "Mauritius"),
    ("Egypt", "Egypt"),
    ("Ethiopia", "Ethiopia"),
    ("Kenya", "Kenya"),
    ("Finland", "Finland"),
    ("Poland", "Poland"),
    ("South Africa", "South Africa"),
    ("New Zealand", "New Zealand"),
    ("Russia", "Russia"),
    ("Brazil", "Brazil"),
    ("Other", "Other Nationality"),
]

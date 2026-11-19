"""Turkish 81-province centroids and pure-Python UTM/WGS84 PDF coordinate extraction."""

from __future__ import annotations

import hashlib
import math
import re
from typing import Any

# Approximate centroids (lat, lon) for all 81 provinces of Türkiye
PROVINCE_CENTROIDS: dict[str, tuple[float, float]] = {
    "ADANA": (37.0000, 35.3213),
    "ADIYAMAN": (37.7648, 38.2786),
    "AFYONKARAHİSAR": (38.7507, 30.5567),
    "AFYON": (38.7507, 30.5567),
    "AĞRI": (39.7191, 43.0503),
    "AKSARAY": (38.3687, 34.0370),
    "AMASYA": (40.6499, 35.8353),
    "ANKARA": (39.9334, 32.8597),
    "ANTALYA": (36.8969, 30.7133),
    "ARDAHAN": (41.1105, 42.7022),
    "ARTVİN": (41.1828, 41.8183),
    "AYDIN": (37.8560, 27.8416),
    "BALIKESİR": (39.6484, 27.8826),
    "BARTIN": (41.6344, 32.3375),
    "BATMAN": (37.8812, 41.1351),
    "BAYBURT": (40.2552, 40.2249),
    "BİLECİK": (40.1451, 29.9799),
    "BİNGÖL": (38.8855, 40.4966),
    "BİTLİS": (38.4006, 42.1095),
    "BOLU": (40.7350, 31.6061),
    "BURDUR": (37.7203, 30.2908),
    "BURSA": (40.1885, 29.0610),
    "ÇANAKKALE": (40.1553, 26.4142),
    "ÇANKIRI": (40.6013, 33.6134),
    "ÇORUM": (40.5506, 34.9556),
    "DENİZLİ": (37.7765, 29.0864),
    "DİYARBAKIR": (37.9144, 40.2306),
    "DÜZCE": (40.8438, 31.1565),
    "EDİRNE": (41.6771, 26.5557),
    "ELAZIĞ": (38.6810, 39.2264),
    "ERZİNCAN": (39.7500, 39.5000),
    "ERZURUM": (39.9043, 41.2679),
    "ESKİŞEHİR": (39.7767, 30.5206),
    "GAZİANTEP": (37.0662, 37.3833),
    "GİRESUN": (40.9128, 38.3895),
    "GÜMÜŞHANE": (40.4603, 39.4814),
    "HAKKARİ": (37.5833, 43.7333),
    "HATAY": (36.2023, 36.1613),
    "IĞDIR": (39.9167, 44.0333),
    "ISPARTA": (37.7648, 30.5566),
    "İSTANBUL": (41.0082, 28.9784),
    "İZMİR": (38.4237, 27.1428),
    "KAHRAMANMARAŞ": (37.5858, 36.9371),
    "KARABÜK": (41.2061, 32.6204),
    "KARAMAN": (37.1759, 33.2287),
    "KARS": (40.6013, 43.0975),
    "KASTAMONU": (41.3887, 33.7827),
    "KAYSERİ": (38.7312, 35.4787),
    "KIRIKKALE": (39.8468, 33.5153),
    "KIRKLARELİ": (41.7333, 27.2167),
    "KIRŞEHİR": (39.1425, 34.1709),
    "KİLİS": (36.7184, 37.1212),
    "KOCAELİ": (40.8533, 29.8815),
    "KONYA": (37.8746, 32.4932),
    "KÜTAHYA": (39.4167, 29.9833),
    "MALATYA": (38.3552, 38.3095),
    "MANİSA": (38.6191, 27.4289),
    "MARDİN": (37.3212, 40.7245),
    "MERSİN": (36.8121, 34.6415),
    "İÇEL": (36.8121, 34.6415),
    "MUĞLA": (37.2153, 28.3636),
    "MUŞ": (38.7432, 41.5064),
    "NEVŞEHİR": (38.6244, 34.7239),
    "NİĞDE": (37.9667, 34.6833),
    "ORDU": (40.9839, 37.8764),
    "OSMANİYE": (37.0742, 36.2478),
    "RİZE": (41.0201, 40.5234),
    "SAKARYA": (40.7569, 30.3783),
    "SAMSUN": (41.2867, 36.3300),
    "SİİRT": (37.9333, 41.9500),
    "SİNOP": (42.0231, 35.1531),
    "SİVAS": (39.7477, 37.0179),
    "ŞANLIURFA": (37.1674, 38.7955),
    "ŞIRNAK": (37.5164, 42.4611),
    "TEKİRDAĞ": (40.9781, 27.5117),
    "TOKAT": (40.3167, 36.5500),
    "TRABZON": (41.0027, 39.7168),
    "TUNCELİ": (39.1079, 39.5401),
    "UŞAK": (38.6823, 29.4082),
    "VAN": (38.4891, 43.4089),
    "YALOVA": (40.6500, 29.2667),
    "YOZGAT": (39.8181, 34.8147),
    "ZONGULDAK": (41.4564, 31.7987),
}


def normalize_province(name: str) -> str:
    return name.replace("i", "İ").replace("ı", "I").upper().strip()


def province_centroid(province: str, jitter_key: str | None = None) -> tuple[float, float]:
    """Return province centroid with optional small deterministic jitter so markers don't overlap."""
    base = PROVINCE_CENTROIDS.get(normalize_province(province), (39.0, 35.2))
    if not jitter_key:
        return base
    h = hashlib.sha1(jitter_key.encode("utf-8")).digest()
    dlat = ((h[0] / 255.0) - 0.5) * 0.14
    dlon = ((h[1] / 255.0) - 0.5) * 0.16
    return (round(base[0] + dlat, 5), round(base[1] + dlon, 5))


def utm_to_wgs84(easting: float, northing: float, zone: int, datum: str = "WGS84") -> tuple[float, float]:
    """Convert UTM (Zone 35..38 North) coordinates to WGS84 (lat, lon) in degrees."""
    a = 6378137.0
    e2 = 0.00669437999014
    e1 = (1 - math.sqrt(1 - e2)) / (1 + math.sqrt(1 - e2))
    k0 = 0.9996

    x = easting - 500000.0
    y = northing
    m = y / k0
    mu = m / (a * (1 - e2 / 4 - 3 * e2**2 / 64 - 5 * e2**3 / 256))

    phi1 = (
        mu
        + (3 * e1 / 2 - 27 * e1**3 / 32) * math.sin(2 * mu)
        + (21 * e1**2 / 16 - 55 * e1**4 / 32) * math.sin(4 * mu)
        + (151 * e1**3 / 96) * math.sin(6 * mu)
        + (1097 * e1**4 / 512) * math.sin(8 * mu)
    )

    ep2 = e2 / (1 - e2)
    c1 = ep2 * math.cos(phi1) ** 2
    t1 = math.tan(phi1) ** 2
    n1 = a / math.sqrt(1 - e2 * math.sin(phi1) ** 2)
    r1 = a * (1 - e2) / ((1 - e2 * math.sin(phi1) ** 2) ** 1.5)
    d = x / (n1 * k0)

    lat = phi1 - (n1 * math.tan(phi1) / r1) * (
        d**2 / 2
        - (5 + 3 * t1 + 10 * c1 - 4 * c1**2 - 9 * ep2) * d**4 / 24
        + (61 + 90 * t1 + 298 * c1 + 45 * t1**2 - 252 * ep2 - 3 * c1**2) * d**6 / 720
    )

    lon0 = math.radians((zone - 1) * 6 - 180 + 3)
    lon = lon0 + (
        d
        - (1 + 2 * t1 + c1) * d**3 / 6
        + (5 - 2 * c1 + 28 * t1 - 3 * c1**2 + 8 * ep2 + 24 * t1**2) * d**5 / 120
    ) / math.cos(phi1)

    lat_deg = math.degrees(lat)
    lon_deg = math.degrees(lon)

    # Approximate ED50 -> WGS84 datum shift for Türkiye (~ -0.00095° lat, -0.00105° lon)
    if datum.upper() == "ED50":
        lat_deg -= 0.00095
        lon_deg -= 0.00105
    return (round(lat_deg, 6), round(lon_deg, 6))


def _utm_zones_for_lon(lon: float) -> list[int]:
    primary = int(math.floor((lon + 180.0) / 6.0)) + 1
    zones = [primary]
    for adj in (primary - 1, primary + 1):
        if 35 <= adj <= 38 and adj not in zones:
            zones.append(adj)
    return zones


def _parse_tr_float(num_str: str) -> float | None:
    s = num_str.strip()
    # Handle 4.285.123,45 or 4285123.45 or 4285123,45
    if s.count(".") >= 2:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def extract_pdf_coordinates(page_texts: list[str], province: str) -> dict[str, Any]:
    """Extract plausible exact project coordinates from Turkish ÇED/PTD PDF text."""
    ref_lat, ref_lon = province_centroid(province)
    candidate_zones = _utm_zones_for_lon(ref_lon)

    def near_province(lat: float, lon: float) -> bool:
        return (
            35.7 <= lat <= 42.3
            and 25.5 <= lon <= 45.0
            and abs(lat - ref_lat) <= 1.65
            and abs(lon - ref_lon) <= 1.85
        )

    points: list[tuple[float, float]] = []
    source_pages: list[int] = []
    seen_pts: set[tuple[float, float]] = set()
    detected_datum = "WGS84"

    # Pattern 1: UTM Easting (6 digits, 160000..840000) and Northing (7 digits, 3950000..4690000) in either order
    utm_pair_re = re.compile(
        r"(?<!\d)(\d{6}(?:[.,]\d{1,3})?|\d{3}\.\d{3}(?:,\d{1,3})?)"
        r"[\s;,|/:\t]{1,18}"
        r"(\d{7}(?:[.,]\d{1,3})?|\d\.\d{3}\.\d{3}(?:,\d{1,3})?)(?!\d)"
    )
    utm_rev_re = re.compile(
        r"(?<!\d)(\d{7}(?:[.,]\d{1,3})?|\d\.\d{3}\.\d{3}(?:,\d{1,3})?)"
        r"[\s;,|/:\t]{1,18}"
        r"(\d{6}(?:[.,]\d{1,3})?|\d{3}\.\d{3}(?:,\d{1,3})?)(?!\d)"
    )
    # Pattern 2: WGS84 decimal degrees inside Türkiye (36..42 N, 26..44 E)
    dd_re = re.compile(
        r"(?<!\d)(3[6-9][.,]\d{4,7}|4[0-2][.,]\d{4,7})"
        r"[\s;,|/:\t°KkNn]{1,12}"
        r"(2[6-9][.,]\d{4,7}|3\d[.,]\d{4,7}|4[0-4][.,]\d{4,7})(?!\d)"
    )

    for pno, txt in enumerate(page_texts, start=1):
        low = txt.lower()
        if "koordinat" not in low and "utm" not in low and "ed50" not in low and "ed-50" not in low and "itrf" not in low and "wgs" not in low:
            continue
        page_datum = "ED50" if ("ed50" in low or "ed-50" in low or "ed 50" in low) else "WGS84"

        # Try explicit WGS84 decimal degrees first
        for m in dd_re.finditer(txt):
            lat = _parse_tr_float(m.group(1))
            lon = _parse_tr_float(m.group(2))
            if lat is not None and lon is not None and near_province(lat, lon):
                pt = (round(lat, 5), round(lon, 5))
                if pt not in seen_pts:
                    seen_pts.add(pt)
                    points.append(pt)
                    if pno not in source_pages:
                        source_pages.append(pno)
                    if len(points) >= 80:
                        break

        if len(points) >= 80:
            break

        # Try UTM pairs (Easting, Northing) and (Northing, Easting)
        for rx, rev in ((utm_pair_re, False), (utm_rev_re, True)):
            for m in rx.finditer(txt):
                a_val = _parse_tr_float(m.group(1))
                b_val = _parse_tr_float(m.group(2))
                if a_val is None or b_val is None:
                    continue
                easting, northing = (b_val, a_val) if rev else (a_val, b_val)
                if not (160_000 <= easting <= 840_000 and 3_950_000 <= northing <= 4_690_000):
                    continue
                for z in candidate_zones:
                    lat, lon = utm_to_wgs84(easting, northing, z, datum=page_datum)
                    if near_province(lat, lon):
                        pt = (round(lat, 5), round(lon, 5))
                        if pt not in seen_pts:
                            seen_pts.add(pt)
                            points.append(pt)
                            detected_datum = f"UTM-Z{z}/{page_datum}"
                            if pno not in source_pages:
                                source_pages.append(pno)
                        break
                if len(points) >= 80:
                    break
            if len(points) >= 80:
                break

    if points:
        avg_lat = round(sum(p[0] for p in points) / len(points), 5)
        avg_lon = round(sum(p[1] for p in points) / len(points), 5)
        return {
            "precision": "exact_pdf",
            "lat": avg_lat,
            "lon": avg_lon,
            "point_count": len(points),
            "points": points[:40],
            "datum": detected_datum,
            "pages": source_pages[:10],
        }

    return {
        "precision": "province_centroid",
        "lat": ref_lat,
        "lon": ref_lon,
        "point_count": 0,
        "points": [],
        "datum": None,
        "pages": [],
    }

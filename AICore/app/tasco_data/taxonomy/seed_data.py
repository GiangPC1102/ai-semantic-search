# Minimal, stable taxonomy seed per plan section 10.
# Each entry: (alias_type, alias_text, target_id, target_display, constraint_default, is_hard_capable)

CATEGORY_SEED = [
    ("category", "cafe", "cafe", "Cafe", "hard", True),
    ("category", "quan ca phe", "cafe", "Cafe", "hard", True),
    ("category", "coffee shop", "cafe", "Cafe", "hard", True),
    ("category", "restaurant", "restaurant", "Nha hang", "hard", True),
    ("category", "nha hang", "restaurant", "Nha hang", "hard", True),
    ("category", "quan an", "restaurant", "Nha hang", "hard", True),
    ("category", "hotel", "hotel", "Khach san", "hard", True),
    ("category", "khach san", "hotel", "Khach san", "hard", True),
    ("category", "atm", "atm", "ATM", "hard", True),
    ("category", "gas station", "gas_station", "Tram xang", "hard", True),
    ("category", "tram xang", "gas_station", "Tram xang", "hard", True),
    ("category", "mall", "mall", "Trung tam thuong mai", "hard", True),
    ("category", "trung tam thuong mai", "mall", "Trung tam thuong mai", "hard", True),
    ("category", "pharmacy", "pharmacy", "Nha thuoc", "hard", True),
    ("category", "nha thuoc", "pharmacy", "Nha thuoc", "hard", True),
]

ATTRIBUTE_SEED = [
    ("attribute", "wifi", "wifi", "Wifi", "hard", True),
    ("attribute", "parking", "parking", "Bai do xe", "hard", True),
    ("attribute", "bai do xe", "parking", "Bai do xe", "hard", True),
    ("attribute", "cho dau xe", "parking", "Bai do xe", "hard", True),
    ("attribute", "toilet", "toilet", "Toilet", "hard", True),
    ("attribute", "swimming pool", "swimming_pool", "Ho boi", "hard", True),
    ("attribute", "ho boi", "swimming_pool", "Ho boi", "hard", True),
    ("attribute", "quiet", "quiet", "Yen tinh", "soft", False),
    ("attribute", "yen tinh", "quiet", "Yen tinh", "soft", False),
    ("attribute", "nice view", "nice_view", "View dep", "soft", False),
    ("attribute", "view dep", "nice_view", "View dep", "soft", False),
    ("attribute", "romantic", "romantic", "Lang man", "soft", False),
    ("attribute", "lang man", "romantic", "Lang man", "soft", False),
    ("attribute", "family friendly", "family_friendly", "Phu hop gia dinh", "soft", False),
    ("attribute", "phu hop gia dinh", "family_friendly", "Phu hop gia dinh", "soft", False),
    ("attribute", "open late", "open_late", "Mo khuya", "soft", False),
    ("attribute", "mo khuya", "open_late", "Mo khuya", "soft", False),
]

INTENT_SEED = [
    ("intent", "phu hop lam viec", "work_or_study", "Phu hop lam viec/hoc bai", "inferred", False),
    ("intent", "phu hop hoc bai", "work_or_study", "Phu hop lam viec/hoc bai", "inferred", False),
    ("intent", "hen ho", "date_night", "Hen ho", "inferred", False),
    ("intent", "phu hop hen ho", "date_night", "Hen ho", "inferred", False),
    ("intent", "phu hop gia dinh", "family_kids", "Phu hop gia dinh/tre em", "inferred", False),
    ("intent", "check in", "tourist_checkin", "Tham quan/check-in", "inferred", False),
    ("intent", "phu hop du lich", "tourist_checkin", "Tham quan/check-in", "inferred", False),
    ("intent", "an khuya", "late_night_food", "An khuya", "inferred", False),
    ("intent", "khach san bien", "beach_hotel", "Khach san/resort bien", "inferred", False),
]

MINIMAL_TAXONOMY_SEED = CATEGORY_SEED + ATTRIBUTE_SEED + INTENT_SEED

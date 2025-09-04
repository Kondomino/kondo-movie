import re
from typing import Dict, List
from functools import reduce

def camel_to_snake(str): 
    return reduce(lambda x, y: x + ('_' if y.isupper() else '') + y, str).lower()

# Common street abbreviations for URL generation and address normalization
STREET_ABBREVIATIONS = {
    'STREET': 'ST',
    'AVENUE': 'AVE', 
    'AVENUES': 'AVES',
    'BOULEVARD': 'BLVD',
    'BOULEVARDS': 'BLVDS',
    'DRIVE': 'DR',
    'DRIVES': 'DRS',
    'PLACE': 'PL',
    'PLACES': 'PLS',
    'ROAD': 'RD',
    'ROADS': 'RDS',
    'COURT': 'CT',
    'COURTS': 'CTS',
    'LANE': 'LN',
    'LANES': 'LNS',
    'CIRCLE': 'CIR',
    'CIRCLES': 'CIRS',
    'WAY': 'WAY',
    'WAYS': 'WAYS',
    'TERRACE': 'TER',
    'TERRACES': 'TERS',
    'PARKWAY': 'PKWY',
    'PARKWAYS': 'PKWYS',
    'HIGHWAY': 'HWY',
    'HIGHWAYS': 'HWYS',
    'NORTH': 'N',
    'SOUTH': 'S', 
    'EAST': 'E',
    'WEST': 'W',
    'NORTHEAST': 'NE',
    'NORTHWEST': 'NW',
    'SOUTHEAST': 'SE',
    'SOUTHWEST': 'SW'
}

def apply_street_abbreviations(text: str) -> str:
    """
    Apply street abbreviations to a given text.
    
    Args:
        text: The text to apply abbreviations to
        
    Returns:
        The text with street abbreviations applied
    """
    result = text.upper()
    for full_word, abbrev in STREET_ABBREVIATIONS.items():
        result = result.replace(full_word, abbrev)
    return result

def generate_url_slugs(title: str) -> List[str]:
    """
    Generate multiple URL slug formats from a property title.
    
    Args:
        title: The property title to convert to slugs
        
    Returns:
        List of different slug formats to try
    """
    import re
    
    # Format 1: Remove special characters and convert spaces to hyphens
    slug_with_hyphens = re.sub(r'[^a-zA-Z0-9\s-]', '', title.lower())
    slug_with_hyphens = re.sub(r'\s+', '-', slug_with_hyphens.strip())
    
    # Format 2: Remove special characters and spaces entirely
    slug_no_spaces = re.sub(r'[^a-zA-Z0-9]', '', title.lower())
    
    # Format 3: Apply street abbreviations and convert spaces to hyphens
    title_with_abbrev = apply_street_abbreviations(title)
    slug_with_abbreviations = re.sub(r'[^a-zA-Z0-9\s-]', '', title_with_abbrev.lower())
    slug_with_abbreviations = re.sub(r'\s+', '-', slug_with_abbreviations.strip())
    
    # Format 4: Apply street abbreviations and remove spaces entirely
    slug_abbrev_no_spaces = re.sub(r'[^a-zA-Z0-9]', '', title_with_abbrev.lower())
    
    return [
        slug_with_hyphens,
        slug_no_spaces,
        slug_with_abbreviations,
        slug_abbrev_no_spaces
    ]

DIRECTIONAL_ABBREVIATIONS = {
    'NORTH': ['N', 'N.'],
    'SOUTH': ['S', 'S.'],
    'EAST': ['E', 'E.'],
    'WEST': ['W', 'W.'],
    'NORTHEAST': ['NE', 'NE.'],
    'NORTHWEST': ['NW', 'NW.'],
    'SOUTHEAST': ['SE', 'SE.'],
    'SOUTHWEST': ['SW', 'SW.'],
}

# Reverse mappings for converting abbreviations back to full format
ABBREVIATIONS_TO_FULL = {
    # Street type abbreviations
    'RD': 'ROAD',
    'RD.': 'ROAD',
    'ST': 'STREET',
    'ST.': 'STREET',
    'AVE': 'AVENUE',
    'AVE.': 'AVENUE',
    'BLVD': 'BOULEVARD',
    'BLVD.': 'BOULEVARD',
    'DR': 'DRIVE',
    'DR.': 'DRIVE',
    'PL': 'PLACE',
    'PL.': 'PLACE',
    'CT': 'COURT',
    'CT.': 'COURT',
    'LN': 'LANE',
    'LN.': 'LANE',
    'CIR': 'CIRCLE',
    'CIR.': 'CIRCLE',
    'TER': 'TERRACE',
    'TER.': 'TERRACE',
    'PKWY': 'PARKWAY',
    'PKWY.': 'PARKWAY',
    'HWY': 'HIGHWAY',
    'HWY.': 'HIGHWAY',
    # Directional abbreviations
    'N': 'NORTH',
    'N.': 'NORTH',
    'S': 'SOUTH',
    'S.': 'SOUTH',
    'E': 'EAST',
    'E.': 'EAST',
    'W': 'WEST',
    'W.': 'WEST',
    'NE': 'NORTHEAST',
    'NE.': 'NORTHEAST',
    'NW': 'NORTHWEST',
    'NW.': 'NORTHWEST',
    'SE': 'SOUTHEAST',
    'SE.': 'SOUTHEAST',
    'SW': 'SOUTHWEST',
    'SW.': 'SOUTHWEST',
}

STREET_TYPE_ABBREVIATIONS = {
    'AVENUE': ['AVE', 'AVE.'],
    'BOULEVARD': ['BLVD', 'BLVD.'],
    'DRIVE': ['DR', 'DR.'],
    'PLACE': ['PL', 'PL.'],
    'ROAD': ['RD', 'RD.'],
    'COURT': ['CT', 'CT.'],
    'LANE': ['LN', 'LN.'],
    'CIRCLE': ['CIR', 'CIR.'],
    'TERRACE': ['TER', 'TER.'],
    'PARKWAY': ['PKWY', 'PKWY.'],
    'HIGHWAY': ['HWY', 'HWY.'],
    # Add more as needed
}

def convert_abbreviations_to_full_format(text: str) -> str:
    """
    Convert abbreviated street address to full format (RD -> ROAD, etc.)
    
    Args:
        text: The text to convert from abbreviations to full format
        
    Returns:
        The text with abbreviations converted to full format
    """
    import re
    
    full_format = text.upper()
    
    # Use word boundaries to only replace whole words, not parts of words
    for abbrev, full in ABBREVIATIONS_TO_FULL.items():
        # Use word boundary regex to ensure we only replace whole words
        pattern = r'\b' + re.escape(abbrev) + r'\b'
        full_format = re.sub(pattern, full, full_format)
    
    return full_format

def generate_all_abbreviation_variants(text: str) -> list:
    """
    Generate all variants of an address string with/without periods for directionals and street types,
    and also with the street type removed entirely.
    """
    variants = set()
    base = text.upper()
    variants.add(base)
    # Directionals
    for full, abbrs in DIRECTIONAL_ABBREVIATIONS.items():
        if full in base:
            for abbr in abbrs:
                variants.add(base.replace(full, abbr))
    # Street types
    for full, abbrs in STREET_TYPE_ABBREVIATIONS.items():
        if full in base:
            for abbr in abbrs:
                variants.add(base.replace(full, abbr))
            # Also add variant with the street type removed entirely
            variants.add(base.replace(full, '').strip())
    # For each variant, also add a title-cased version (for search sensitivity)
    more_variants = set()
    for v in variants:
        v_clean = ' '.join(v.split())  # Remove extra spaces
        more_variants.add(v_clean)
        more_variants.add(v_clean.title())
    return list(more_variants)
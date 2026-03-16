"""
Tool functions for Sam the Som — sommelier agent.
Provides memory, cellar inventory, and consumed wines management.
"""

from typing import List, Dict, Any
import os
from .sheet_utilities import get_sheets_connector, get_docs_connector


# ---------------------------------------------------------------------------
# Sheet tab names and ranges
# ---------------------------------------------------------------------------
CELLAR_TAB = 'My Bottles'
CONSUMED_TAB = 'My Consumed Bottles'
TASTING_NOTES_TAB = 'My Tasting Notes'

# ---------------------------------------------------------------------------
# Cellar spreadsheet column headers (47 columns, in order)
# ---------------------------------------------------------------------------
CELLAR_HEADERS = [
    'iInventory', 'Pending', 'Barcode', 'WineBarcode', 'Currency',
    'ExchangeRate', 'Value', 'Price', 'NativePrice', 'NativePriceCurrency',
    'Size', 'iWine', 'Type', 'Color', 'Category', 'Vintage', 'Wine',
    'Locale', 'Producer', 'Varietal', 'MasterVarietal', 'Designation',
    'Vineyard', 'Country', 'Region', 'SubRegion', 'Appellation', 'Note',
    'StoreName', 'PurchaseDate', 'DeliveryDate', 'PurchaseNote', 'Location',
    'Bin', 'BeginConsume', 'EndConsume', 'WindowSource', 'BarcodePrinted',
    'LikeVotes', 'LikePercent', 'LikeIt', 'PNotes', 'PScore', 'CScore',
    'JS', 'JSBegin', 'JSEnd',
]

# Consumed wines spreadsheet column headers (40 columns, in order)
CONSUMED_HEADERS = [
    'iConsumed', 'iWine', 'Type', 'Consumed', 'ConsumedYear',
    'ConsumedQuarter', 'ConsumedMonth', 'ConsumedDay', 'ConsumedWeekday',
    'Size', 'ShortType', 'Currency', 'ExchangeRate', 'Value', 'Price',
    'NativePrice', 'NativePriceCurrency', 'NativeRevenue',
    'NativeRevenueCurrency', 'Revenue', 'RevenueCurrency',
    'RevenueExchangeRate', 'ConsumptionNote', 'PurchaseNote', 'BottleNote',
    'Location', 'Bin', 'Vintage', 'Wine', 'Locale', 'Color', 'Category',
    'Varietal', 'MasterVarietal', 'Designation', 'Vineyard', 'Country',
    'Region', 'SubRegion', 'Appellation',
]

# Tasting notes spreadsheet column headers (35 columns, in order)
TASTING_NOTES_HEADERS = [
    'iNote', 'iWine', 'Reviewer', 'Type', 'Vintage', 'Wine', 'Locale',
    'Producer', 'Varietal', 'MasterVarietal', 'Designation', 'Vineyard',
    'Country', 'Region', 'SubRegion', 'Appellation', 'TastingDate',
    'Defective', 'Views', 'fHelpful', 'fFavorite', 'Rating',
    'EventLocation', 'EventTitle', 'iEvent', 'EventDate', 'EventEndDate',
    'TastingNotes', 'fLikeIt', 'CNotes', 'CScore', 'LikeVotes',
    'LikePercent', 'Votes', 'Comments',
]


# ---------------------------------------------------------------------------
# Memory tools
# ---------------------------------------------------------------------------

def get_sommelier_memory() -> str:
    """
    Retrieve Sam's working memory from the Google Doc.

    This document contains everything Sam knows about users, their
    preferences, cellar audit history, recent recommendations, and
    conversation notes. Sam should call this at the start of every
    conversation.

    Returns:
        The full text content of the memory document.
    """
    doc_id = os.getenv('SOMMELIER_MEMORY_DOC_ID')
    if not doc_id:
        raise ValueError("SOMMELIER_MEMORY_DOC_ID environment variable not set")

    connector = get_docs_connector()
    return connector.read_doc(doc_id)


def update_sommelier_memory(updated_memory: str) -> Dict[str, Any]:
    """
    Update Sam's working memory in the Google Doc.

    Replaces the full content of the memory document with the provided
    updated memory text. Sam should call this at the end of every
    meaningful conversation to persist new learnings.

    Args:
        updated_memory: The complete revised memory document text to write.

    Returns:
        Response from the API confirming the update.
    """
    doc_id = os.getenv('SOMMELIER_MEMORY_DOC_ID')
    if not doc_id:
        raise ValueError("SOMMELIER_MEMORY_DOC_ID environment variable not set")

    connector = get_docs_connector()
    return connector.write_doc(doc_id, updated_memory)


# ---------------------------------------------------------------------------
# Cellar inventory tools
# ---------------------------------------------------------------------------

def get_cellar_inventory(location: str = "") -> Dict[str, Any]:
    """
    Retrieve the wine cellar inventory.

    Reads all wines from the cellar spreadsheet. Each row represents a
    single bottle. If location is provided, only wines at that location
    are returned.

    Args:
        location: Optional filter — e.g. "NYC", "Poconos". Case-insensitive.
                  Leave empty to get all wines.

    Returns:
        Dictionary with 'headers' (list of column names) and 'wines'
        (list of dicts, one per bottle).
    """
    spreadsheet_id = os.getenv('SOMMELIER_CELLAR_SSID')
    if not spreadsheet_id:
        raise ValueError("SOMMELIER_CELLAR_SSID environment variable not set")

    connector = get_sheets_connector()
    rows = connector.read_sheet(spreadsheet_id, f"'{CELLAR_TAB}'!A:AW")

    if not rows or len(rows) < 2:
        return {'headers': CELLAR_HEADERS, 'wines': [], 'total': 0}

    headers = rows[0]
    wines = []
    for row in rows[1:]:
        wine = {headers[i]: row[i] if i < len(row) else '' for i in range(len(headers))}
        if location:
            if wine.get('Location', '').lower() != location.lower():
                continue
        wines.append(wine)

    return {'headers': headers, 'wines': wines, 'total': len(wines)}


def search_cellar(query: str) -> Dict[str, Any]:
    """
    Search the wine cellar for bottles matching a query.

    Searches across Wine name, Producer, Varietal, Region, SubRegion,
    Appellation, Country, and Vintage fields. Case-insensitive partial
    matching.

    Args:
        query: Search term — e.g. "Barolo", "Cabernet", "2018", "Opus One".

    Returns:
        Dictionary with 'headers', 'wines' (matching bottles), 'total',
        and 'row_numbers' (1-based sheet row numbers for each match, useful
        for remove_wine_from_cellar).
    """
    spreadsheet_id = os.getenv('SOMMELIER_CELLAR_SSID')
    if not spreadsheet_id:
        raise ValueError("SOMMELIER_CELLAR_SSID environment variable not set")

    connector = get_sheets_connector()
    rows = connector.read_sheet(spreadsheet_id, f"'{CELLAR_TAB}'!A:AW")

    if not rows or len(rows) < 2:
        return {'headers': CELLAR_HEADERS, 'wines': [], 'total': 0, 'row_numbers': []}

    headers = rows[0]
    search_fields = ['Wine', 'Producer', 'Varietal', 'MasterVarietal',
                     'Region', 'SubRegion', 'Appellation', 'Country',
                     'Vintage', 'Location', 'Bin']
    search_indices = [headers.index(f) for f in search_fields if f in headers]

    query_lower = query.lower()
    matches = []
    row_numbers = []

    for row_idx, row in enumerate(rows[1:], start=2):  # row 2 is first data row
        for col_idx in search_indices:
            if col_idx < len(row) and query_lower in row[col_idx].lower():
                wine = {headers[i]: row[i] if i < len(row) else '' for i in range(len(headers))}
                matches.append(wine)
                row_numbers.append(row_idx)
                break

    return {'headers': headers, 'wines': matches, 'total': len(matches), 'row_numbers': row_numbers}


def add_wine_to_cellar(
    Wine: str,
    Vintage: str,
    Producer: str,
    Varietal: str,
    Country: str,
    Region: str,
    Location: str,
    Bin: str = "",
    Value: str = "",
    Price: str = "",
    Color: str = "",
    Type: str = "",
    Category: str = "",
    MasterVarietal: str = "",
    Designation: str = "",
    Vineyard: str = "",
    SubRegion: str = "",
    Appellation: str = "",
    BeginConsume: str = "",
    EndConsume: str = "",
    Size: str = "750ml",
    Note: str = "",
    StoreName: str = "",
    PurchaseDate: str = "",
    JS: str = "",
    PScore: str = "",
    CScore: str = "",
) -> Dict[str, Any]:
    """
    Add a new bottle to the wine cellar spreadsheet.

    Appends a row with the provided wine details. All values should be
    confirmed with the user before calling this function.

    Args:
        Wine: Full wine name (e.g. "Opus One").
        Vintage: Year (e.g. "2018").
        Producer: Producer/winery name.
        Varietal: Grape variety (e.g. "Cabernet Sauvignon").
        Country: Country of origin.
        Region: Wine region (e.g. "Napa Valley").
        Location: Storage location — "NYC" or "Poconos".
        Bin: Bin/shelf position in cellar (optional).
        Value: Estimated value in USD (optional).
        Price: Purchase price in USD (optional).
        Color: "Red", "White", "Rose", "Sparkling", etc. (optional).
        Type: Wine type (optional).
        Category: Wine category (optional).
        MasterVarietal: Broad varietal family (optional).
        Designation: Special designation (optional).
        Vineyard: Specific vineyard (optional).
        SubRegion: Sub-region (optional).
        Appellation: Appellation (optional).
        BeginConsume: Start of drinking window year (optional).
        EndConsume: End of drinking window year (optional).
        Size: Bottle size, default "750ml".
        Note: Any notes about the bottle (optional).
        StoreName: Where it was purchased (optional).
        PurchaseDate: Date purchased (optional).
        JS: James Suckling score (optional).
        PScore: Professional score (optional).
        CScore: Community score (optional).

    Returns:
        Response from the API confirming the append operation.
    """
    spreadsheet_id = os.getenv('SOMMELIER_CELLAR_SSID')
    if not spreadsheet_id:
        raise ValueError("SOMMELIER_CELLAR_SSID environment variable not set")

    # Build row matching the 47-column structure
    new_row = [
        '',             # iInventory (auto or blank)
        '',             # Pending
        '',             # Barcode
        '',             # WineBarcode
        'USD',          # Currency
        '',             # ExchangeRate
        Value,          # Value
        Price,          # Price
        '',             # NativePrice
        '',             # NativePriceCurrency
        Size,           # Size
        '',             # iWine
        Type,           # Type
        Color,          # Color
        Category,       # Category
        Vintage,        # Vintage
        Wine,           # Wine
        '',             # Locale
        Producer,       # Producer
        Varietal,       # Varietal
        MasterVarietal, # MasterVarietal
        Designation,    # Designation
        Vineyard,       # Vineyard
        Country,        # Country
        Region,         # Region
        SubRegion,      # SubRegion
        Appellation,    # Appellation
        Note,           # Note
        StoreName,      # StoreName
        PurchaseDate,   # PurchaseDate
        '',             # DeliveryDate
        '',             # PurchaseNote
        Location,       # Location
        Bin,            # Bin
        BeginConsume,   # BeginConsume
        EndConsume,     # EndConsume
        '',             # WindowSource
        '',             # BarcodePrinted
        '',             # LikeVotes
        '',             # LikePercent
        '',             # LikeIt
        '',             # PNotes
        PScore,         # PScore
        CScore,         # CScore
        JS,             # JS
        '',             # JSBegin
        '',             # JSEnd
    ]

    connector = get_sheets_connector()
    return connector.append_sheet(spreadsheet_id, f"'{CELLAR_TAB}'!A:AW", [new_row])


def remove_wine_from_cellar(row_number: int) -> Dict[str, Any]:
    """
    Remove a bottle from the cellar spreadsheet by deleting its row.

    Use search_cellar() first to find the row_number of the bottle to
    remove. The row_number is 1-based (row 1 = headers, row 2 = first
    wine).

    Args:
        row_number: The 1-based row number to delete (as returned by
                    search_cellar in 'row_numbers').

    Returns:
        Response from the API confirming the deletion.
    """
    spreadsheet_id = os.getenv('SOMMELIER_CELLAR_SSID')
    if not spreadsheet_id:
        raise ValueError("SOMMELIER_CELLAR_SSID environment variable not set")

    connector = get_sheets_connector()
    # Look up the actual sheet ID by name (can't assume it's 0)
    sheet_id = connector.get_sheet_id_by_name(spreadsheet_id, CELLAR_TAB)
    # Convert 1-based row number to 0-based index for the API
    return connector.delete_row(spreadsheet_id, sheet_id=sheet_id, row_index=row_number - 1)


def update_cellar_wine(row_number: int, updates: Dict[str, str]) -> Dict[str, Any]:
    """
    Update specific fields of a single bottle in the cellar spreadsheet.

    Use search_cellar() first to find the row_number. Then pass a dictionary
    of column names and their new values.

    Args:
        row_number: The 1-based row number to update (as returned by
                    search_cellar in 'row_numbers').
        updates: Dictionary mapping column names to new values.
                 Example: {"Location": "NYC", "Bin": "Rack 3", "Value": "85.00"}
                 Only the specified columns will be changed; others are untouched.

    Returns:
        Dictionary with 'updated_fields' listing what was changed, and
        'api_responses' from the API.
    """
    spreadsheet_id = os.getenv('SOMMELIER_CELLAR_SSID')
    if not spreadsheet_id:
        raise ValueError("SOMMELIER_CELLAR_SSID environment variable not set")

    connector = get_sheets_connector()

    # Read headers to map column names to column letters
    header_rows = connector.read_sheet(spreadsheet_id, f"'{CELLAR_TAB}'!1:1")
    if not header_rows:
        raise ValueError("Could not read cellar headers")
    headers = header_rows[0]

    responses = []
    updated = []
    for col_name, new_value in updates.items():
        if col_name not in headers:
            continue
        col_idx = headers.index(col_name)
        col_letter = _col_index_to_letter(col_idx)
        cell_range = f"'{CELLAR_TAB}'!{col_letter}{row_number}"
        resp = connector.write_sheet(spreadsheet_id, cell_range, [[new_value]])
        responses.append(resp)
        updated.append(col_name)

    return {'updated_fields': updated, 'row_number': row_number, 'api_responses': responses}


def update_cellar_wines_batch(
    Wine: str,
    Vintage: str,
    Producer: str,
    MasterVarietal: str,
    updates: Dict[str, str],
) -> Dict[str, Any]:
    """
    Update specific fields on ALL bottles matching the given Wine, Vintage,
    Producer, and MasterVarietal combination.

    Use this when the user wants to update a shared attribute across all
    identical bottles (e.g. changing the Location or Bin for all 6 bottles
    of the same wine). Sam should ALWAYS ask the user whether they want to
    update just one bottle or all matching bottles before calling this.

    Args:
        Wine: Exact wine name to match.
        Vintage: Exact vintage to match.
        Producer: Exact producer to match.
        MasterVarietal: Exact master varietal to match.
        updates: Dictionary mapping column names to new values.
                 Example: {"Location": "NYC", "Bin": "Rack 3"}

    Returns:
        Dictionary with 'matched_count', 'updated_row_numbers', and
        'updated_fields'.
    """
    spreadsheet_id = os.getenv('SOMMELIER_CELLAR_SSID')
    if not spreadsheet_id:
        raise ValueError("SOMMELIER_CELLAR_SSID environment variable not set")

    connector = get_sheets_connector()
    rows = connector.read_sheet(spreadsheet_id, f"'{CELLAR_TAB}'!A:AW")

    if not rows or len(rows) < 2:
        return {'matched_count': 0, 'updated_row_numbers': [], 'updated_fields': []}

    headers = rows[0]

    # Find indices for matching fields
    wine_idx = headers.index('Wine') if 'Wine' in headers else None
    vintage_idx = headers.index('Vintage') if 'Vintage' in headers else None
    producer_idx = headers.index('Producer') if 'Producer' in headers else None
    mv_idx = headers.index('MasterVarietal') if 'MasterVarietal' in headers else None

    if any(idx is None for idx in [wine_idx, vintage_idx, producer_idx, mv_idx]):
        raise ValueError("Required matching columns not found in headers")

    # Find all matching rows
    matching_rows = []
    for row_idx, row in enumerate(rows[1:], start=2):
        row_wine = row[wine_idx] if wine_idx < len(row) else ''
        row_vintage = row[vintage_idx] if vintage_idx < len(row) else ''
        row_producer = row[producer_idx] if producer_idx < len(row) else ''
        row_mv = row[mv_idx] if mv_idx < len(row) else ''

        if (row_wine == Wine and row_vintage == Vintage and
                row_producer == Producer and row_mv == MasterVarietal):
            matching_rows.append(row_idx)

    if not matching_rows:
        return {'matched_count': 0, 'updated_row_numbers': [], 'updated_fields': []}

    # Apply updates to each matching row
    updated_fields = []
    for col_name, new_value in updates.items():
        if col_name not in headers:
            continue
        col_idx = headers.index(col_name)
        col_letter = _col_index_to_letter(col_idx)

        for row_num in matching_rows:
            cell_range = f"'{CELLAR_TAB}'!{col_letter}{row_num}"
            connector.write_sheet(spreadsheet_id, cell_range, [[new_value]])

        if col_name not in updated_fields:
            updated_fields.append(col_name)

    return {
        'matched_count': len(matching_rows),
        'updated_row_numbers': matching_rows,
        'updated_fields': updated_fields,
    }


def _col_index_to_letter(index: int) -> str:
    """Convert a 0-based column index to a spreadsheet column letter (A, B, ..., Z, AA, AB, ...)."""
    result = ''
    while index >= 0:
        result = chr(index % 26 + ord('A')) + result
        index = index // 26 - 1
    return result


# ---------------------------------------------------------------------------
# Consumed wines tools
# ---------------------------------------------------------------------------

def get_consumed_wines(reviewer: str = "") -> Dict[str, Any]:
    """
    Retrieve consumed wines history.

    Reads all entries from the consumed wines spreadsheet. If reviewer
    is provided, filters to entries where the ConsumptionNote contains
    that reviewer's name.

    Args:
        reviewer: Optional filter — e.g. "Jonathan" or "Nicole".
                  Case-insensitive. Leave empty to get all entries.

    Returns:
        Dictionary with 'headers', 'wines' (list of dicts), and 'total'.
    """
    spreadsheet_id = os.getenv('SOMMELIER_CONSUMED_SSID')
    if not spreadsheet_id:
        raise ValueError("SOMMELIER_CONSUMED_SSID environment variable not set")

    connector = get_sheets_connector()
    rows = connector.read_sheet(spreadsheet_id, f"'{CONSUMED_TAB}'!A:AP")

    if not rows or len(rows) < 2:
        return {'headers': CONSUMED_HEADERS, 'wines': [], 'total': 0}

    headers = rows[0]
    wines = []

    # Find ConsumptionNote column index
    note_idx = headers.index('ConsumptionNote') if 'ConsumptionNote' in headers else None

    for row in rows[1:]:
        wine = {headers[i]: row[i] if i < len(row) else '' for i in range(len(headers))}
        if reviewer and note_idx is not None:
            note = row[note_idx] if note_idx < len(row) else ''
            if reviewer.lower() not in note.lower():
                continue
        wines.append(wine)

    return {'headers': headers, 'wines': wines, 'total': len(wines)}


def add_consumed_wine(
    Wine: str,
    Vintage: str,
    Consumed: str,
    ConsumptionNote: str,
    Location: str = "",
    Value: str = "",
    Price: str = "",
    Color: str = "",
    Type: str = "",
    Category: str = "",
    Varietal: str = "",
    MasterVarietal: str = "",
    Designation: str = "",
    Vineyard: str = "",
    Country: str = "",
    Region: str = "",
    SubRegion: str = "",
    Appellation: str = "",
    Size: str = "750ml",
    iWine: str = "",
    BottleNote: str = "",
    Bin: str = "",
) -> Dict[str, Any]:
    """
    Record a consumed wine in the consumed wines spreadsheet.

    Appends a row with consumption details including tasting notes and
    reviewer attribution. The ConsumptionNote should include who reviewed
    the wine (Jonathan or Nicole) and their tasting notes.

    Args:
        Wine: Full wine name.
        Vintage: Year.
        Consumed: Date consumed (e.g. "3/15/2026").
        ConsumptionNote: Tasting notes including reviewer name, guided by
                         Wine Folly methodology (look, smell, taste, overall).
        Location: Where consumed (e.g. "NYC Cellar", "Poconos", "Restaurant").
        Value: Estimated value in USD (optional).
        Price: Price paid (optional).
        Color: "Red", "White", etc. (optional).
        Type: Wine type (optional).
        Category: Wine category (optional).
        Varietal: Grape variety (optional).
        MasterVarietal: Broad varietal family (optional).
        Designation: Special designation (optional).
        Vineyard: Specific vineyard (optional).
        Country: Country of origin (optional).
        Region: Wine region (optional).
        SubRegion: Sub-region (optional).
        Appellation: Appellation (optional).
        Size: Bottle size, default "750ml".
        iWine: Wine ID from cellar if known (optional).
        BottleNote: Additional bottle notes (optional).
        Bin: Bin location where it was stored (optional).

    Returns:
        Response from the API confirming the append operation.
    """
    spreadsheet_id = os.getenv('SOMMELIER_CONSUMED_SSID')
    if not spreadsheet_id:
        raise ValueError("SOMMELIER_CONSUMED_SSID environment variable not set")

    # Parse consumed date components
    consumed_year = ""
    consumed_month = ""
    consumed_day = ""
    consumed_quarter = ""
    consumed_weekday = ""
    if Consumed:
        try:
            from datetime import datetime
            # Try common date formats
            for fmt in ('%m/%d/%Y', '%Y-%m-%d', '%m-%d-%Y'):
                try:
                    dt = datetime.strptime(Consumed, fmt)
                    consumed_year = str(dt.year)
                    consumed_month = str(dt.month)
                    consumed_day = str(dt.day)
                    consumed_quarter = str((dt.month - 1) // 3 + 1)
                    consumed_weekday = dt.strftime('%A')
                    break
                except ValueError:
                    continue
        except Exception:
            pass

    # Build row matching the 40-column consumed wines structure
    new_row = [
        '',                 # iConsumed (auto or blank)
        iWine,              # iWine
        Type,               # Type
        Consumed,           # Consumed
        consumed_year,      # ConsumedYear
        consumed_quarter,   # ConsumedQuarter
        consumed_month,     # ConsumedMonth
        consumed_day,       # ConsumedDay
        consumed_weekday,   # ConsumedWeekday
        Size,               # Size
        '',                 # ShortType
        'USD',              # Currency
        '',                 # ExchangeRate
        Value,              # Value
        Price,              # Price
        '',                 # NativePrice
        '',                 # NativePriceCurrency
        '',                 # NativeRevenue
        '',                 # NativeRevenueCurrency
        '',                 # Revenue
        '',                 # RevenueCurrency
        '',                 # RevenueExchangeRate
        ConsumptionNote,    # ConsumptionNote
        '',                 # PurchaseNote
        BottleNote,         # BottleNote
        Location,           # Location
        Bin,                # Bin
        Vintage,            # Vintage
        Wine,               # Wine
        '',                 # Locale
        Color,              # Color
        Category,           # Category
        Varietal,           # Varietal
        MasterVarietal,     # MasterVarietal
        Designation,        # Designation
        Vineyard,           # Vineyard
        Country,            # Country
        Region,             # Region
        SubRegion,          # SubRegion
        Appellation,        # Appellation
    ]

    connector = get_sheets_connector()
    return connector.append_sheet(spreadsheet_id, f"'{CONSUMED_TAB}'!A:AP", [new_row])


# ---------------------------------------------------------------------------
# Tasting notes tools
# ---------------------------------------------------------------------------

def get_tasting_notes(reviewer: str = "", wine_name: str = "") -> Dict[str, Any]:
    """
    Retrieve tasting notes and reviews.

    Reads all tasting notes from the tasting notes spreadsheet. Can be
    filtered by reviewer name and/or wine name.

    Args:
        reviewer: Optional filter — e.g. "Jonathan" or "Nicole".
                  Matches against the Reviewer column. Case-insensitive.
        wine_name: Optional filter — search term to match against Wine name.
                   Case-insensitive partial match.

    Returns:
        Dictionary with 'headers', 'notes' (list of dicts), 'total', and
        'row_numbers' (1-based row numbers for use with update/remove).
    """
    spreadsheet_id = os.getenv('SOMMELIER_TASTING_NOTES_SSID')
    if not spreadsheet_id:
        raise ValueError("SOMMELIER_TASTING_NOTES_SSID environment variable not set")

    connector = get_sheets_connector()
    rows = connector.read_sheet(spreadsheet_id, f"'{TASTING_NOTES_TAB}'!A:AK")

    if not rows or len(rows) < 2:
        return {'headers': TASTING_NOTES_HEADERS, 'notes': [], 'total': 0, 'row_numbers': []}

    headers = rows[0]
    notes = []
    row_numbers = []

    reviewer_idx = headers.index('Reviewer') if 'Reviewer' in headers else None
    wine_idx = headers.index('Wine') if 'Wine' in headers else None

    for row_idx, row in enumerate(rows[1:], start=2):  # row 2 is first data row
        if reviewer and reviewer_idx is not None:
            val = row[reviewer_idx] if reviewer_idx < len(row) else ''
            if reviewer.lower() not in val.lower():
                continue

        if wine_name and wine_idx is not None:
            val = row[wine_idx] if wine_idx < len(row) else ''
            if wine_name.lower() not in val.lower():
                continue

        note = {headers[i]: row[i] if i < len(row) else '' for i in range(len(headers))}
        notes.append(note)
        row_numbers.append(row_idx)

    return {'headers': headers, 'notes': notes, 'total': len(notes), 'row_numbers': row_numbers}


def add_tasting_note(
    Reviewer: str,
    Wine: str,
    Vintage: str,
    TastingDate: str,
    TastingNotes: str,
    Rating: str = "",
    Type: str = "",
    Producer: str = "",
    Varietal: str = "",
    MasterVarietal: str = "",
    Country: str = "",
    Region: str = "",
    SubRegion: str = "",
    Appellation: str = "",
    Designation: str = "",
    Vineyard: str = "",
    Locale: str = "",
    iWine: str = "",
    fLikeIt: str = "",
) -> Dict[str, Any]:
    """
    Record a new tasting note in the tasting notes spreadsheet.

    The tasting note should be guided by the Wine Folly methodology:
    look, smell, taste, and overall impression.

    Args:
        Reviewer: Who wrote the review — e.g. "Jonathan" or "Nicole".
        Wine: Full wine name.
        Vintage: Year.
        TastingDate: Date of tasting (e.g. "3/15/2026").
        TastingNotes: The full tasting note text, guided by Wine Folly
                      methodology (look, smell, taste, overall).
        Rating: Numeric rating (e.g. "90") (optional).
        Type: "Red", "White", etc. (optional).
        Producer: Producer/winery name (optional).
        Varietal: Grape variety (optional).
        MasterVarietal: Broad varietal family (optional).
        Country: Country of origin (optional).
        Region: Wine region (optional).
        SubRegion: Sub-region (optional).
        Appellation: Appellation (optional).
        Designation: Special designation (optional).
        Vineyard: Specific vineyard (optional).
        Locale: Full locale string (optional).
        iWine: Wine ID if known (optional).
        fLikeIt: Whether the reviewer liked it — "TRUE" or "FALSE" (optional).

    Returns:
        Response from the API confirming the append operation.
    """
    spreadsheet_id = os.getenv('SOMMELIER_TASTING_NOTES_SSID')
    if not spreadsheet_id:
        raise ValueError("SOMMELIER_TASTING_NOTES_SSID environment variable not set")

    # Build row matching the 35-column tasting notes structure
    new_row = [
        '',             # iNote (auto or blank)
        iWine,          # iWine
        Reviewer,       # Reviewer
        Type,           # Type
        Vintage,        # Vintage
        Wine,           # Wine
        Locale,         # Locale
        Producer,       # Producer
        Varietal,       # Varietal
        MasterVarietal, # MasterVarietal
        Designation,    # Designation
        Vineyard,       # Vineyard
        Country,        # Country
        Region,         # Region
        SubRegion,      # SubRegion
        Appellation,    # Appellation
        TastingDate,    # TastingDate
        'FALSE',        # Defective
        '',             # Views
        '',             # fHelpful
        '',             # fFavorite
        Rating,         # Rating
        '',             # EventLocation
        '',             # EventTitle
        '',             # iEvent
        '',             # EventDate
        '',             # EventEndDate
        TastingNotes,   # TastingNotes
        fLikeIt,        # fLikeIt
        '',             # CNotes
        '',             # CScore
        '',             # LikeVotes
        '',             # LikePercent
        '',             # Votes
        '',             # Comments
    ]

    connector = get_sheets_connector()
    return connector.append_sheet(spreadsheet_id, f"'{TASTING_NOTES_TAB}'!A:AK", [new_row])


def remove_tasting_note(row_number: int) -> Dict[str, Any]:
    """
    Remove a tasting note from the tasting notes spreadsheet by deleting its row.

    Use get_tasting_notes() first to find the row_number of the note to
    remove. The row_number is 1-based (row 1 = headers, row 2 = first note).

    Args:
        row_number: The 1-based row number to delete (as returned by
                    get_tasting_notes in 'row_numbers').

    Returns:
        Response from the API confirming the deletion.
    """
    spreadsheet_id = os.getenv('SOMMELIER_TASTING_NOTES_SSID')
    if not spreadsheet_id:
        raise ValueError("SOMMELIER_TASTING_NOTES_SSID environment variable not set")

    connector = get_sheets_connector()
    # Look up the actual sheet ID by name (can't assume it's 0)
    sheet_id = connector.get_sheet_id_by_name(spreadsheet_id, TASTING_NOTES_TAB)
    # Convert 1-based row number to 0-based index for the API
    return connector.delete_row(spreadsheet_id, sheet_id=sheet_id, row_index=row_number - 1)


def update_tasting_note(row_number: int, updates: Dict[str, str]) -> Dict[str, Any]:
    """
    Update specific fields of a tasting note in the tasting notes spreadsheet.

    Use get_tasting_notes() first to find the row_number. Then pass a dictionary
    of column names and their new values.

    Args:
        row_number: The 1-based row number to update (as returned by
                    get_tasting_notes in 'row_numbers').
        updates: Dictionary mapping column names to new values.
                 Example: {"TastingNotes": "Updated notes...", "Rating": "92"}

    Returns:
        Dictionary with 'updated_cells' count.
    """
    spreadsheet_id = os.getenv('SOMMELIER_TASTING_NOTES_SSID')
    if not spreadsheet_id:
        raise ValueError("SOMMELIER_TASTING_NOTES_SSID environment variable not set")

    connector = get_sheets_connector()
    # Read the header row to map column names to indices
    header_rows = connector.read_sheet(spreadsheet_id, f"'{TASTING_NOTES_TAB}'!1:1")
    if not header_rows:
        raise ValueError("Could not read headers from tasting notes spreadsheet")

    headers = header_rows[0]
    updated_count = 0

    for col_name, new_value in updates.items():
        if col_name not in headers:
            continue
        col_idx = headers.index(col_name)
        col_letter = _col_index_to_letter(col_idx)
        cell_range = f"'{TASTING_NOTES_TAB}'!{col_letter}{row_number}"
        connector.write_sheet(spreadsheet_id, cell_range, [[new_value]])
        updated_count += 1

    return {'updated_cells': updated_count}

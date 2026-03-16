"""
Google Sheets and Google Docs utilities for connecting to Google APIs.
Adapted from growth_coach, generalized for sommelier agent.
"""

from google.auth.transport.requests import Request
from google.oauth2.service_account import Credentials
from google.oauth2 import service_account
from googleapiclient.discovery import build
from google.cloud import secretmanager
import json
import os
from typing import List, Dict, Any, Optional


def get_secret_from_secret_manager(project_id: str, secret_id: str, version_id: str = "latest") -> str:
    """
    Retrieve a secret from Google Cloud Secret Manager.

    Args:
        project_id: Google Cloud project ID.
        secret_id: ID of the secret to retrieve.
        version_id: Version of the secret (default: "latest").

    Returns:
        The secret payload as a string.
    """
    client = secretmanager.SecretManagerServiceClient()
    name = f"projects/{project_id}/secrets/{secret_id}/versions/{version_id}"
    response = client.access_secret_version(request={"name": name})
    return response.payload.data.decode("UTF-8")


def _load_credentials(credentials_path: Optional[str] = None, scopes: Optional[List[str]] = None):
    """Load Google service account credentials from Secret Manager or file."""
    scopes = scopes or [
        'https://www.googleapis.com/auth/spreadsheets',
        'https://www.googleapis.com/auth/drive',
        'https://www.googleapis.com/auth/documents',
    ]

    secret_name = os.getenv('SOMMELIER_SECRET_NAME')
    project_id = os.getenv('GOOGLE_CLOUD_PROJECT')

    if secret_name and project_id:
        credentials_json = get_secret_from_secret_manager(project_id, secret_name)
        credentials_info = json.loads(credentials_json)
        return service_account.Credentials.from_service_account_info(
            credentials_info, scopes=scopes
        )
    else:
        if credentials_path is None:
            credentials_path = os.getenv('SOMMELIER_CREDENTIALS')
        if not credentials_path or not os.path.exists(credentials_path):
            raise ValueError(
                "Credentials not found. Set SOMMELIER_SECRET_NAME for Secret Manager "
                "or SOMMELIER_CREDENTIALS for file-based credentials."
            )
        return service_account.Credentials.from_service_account_file(
            credentials_path, scopes=scopes
        )


class GoogleSheetsConnector:
    """Manages connection to Google Sheets API."""

    def __init__(self, credentials_path: Optional[str] = None, scopes: Optional[List[str]] = None):
        self.scopes = scopes or [
            'https://www.googleapis.com/auth/spreadsheets',
            'https://www.googleapis.com/auth/drive'
        ]
        self.credentials = _load_credentials(credentials_path, self.scopes)
        self.sheets_service = build('sheets', 'v4', credentials=self.credentials)
        self.drive_service = build('drive', 'v3', credentials=self.credentials)

    def read_sheet(self, spreadsheet_id: str, range_name: str) -> List[List[Any]]:
        """Read data from a Google Sheet."""
        result = self.sheets_service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=range_name
        ).execute()
        return result.get('values', [])

    def write_sheet(self, spreadsheet_id: str, range_name: str, values: List[List[Any]]) -> Dict[str, Any]:
        """Write data to a Google Sheet."""
        body = {'values': values}
        result = self.sheets_service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=range_name,
            valueInputOption='RAW',
            body=body
        ).execute()
        return result

    def append_sheet(self, spreadsheet_id: str, range_name: str, values: List[List[Any]]) -> Dict[str, Any]:
        """Append data to a Google Sheet."""
        body = {'values': values}
        result = self.sheets_service.spreadsheets().values().append(
            spreadsheetId=spreadsheet_id,
            range=range_name,
            valueInputOption='RAW',
            body=body
        ).execute()
        return result

    def clear_sheet(self, spreadsheet_id: str, range_name: str) -> Dict[str, Any]:
        """Clear data from a Google Sheet."""
        result = self.sheets_service.spreadsheets().values().clear(
            spreadsheetId=spreadsheet_id,
            range=range_name
        ).execute()
        return result

    def delete_row(self, spreadsheet_id: str, sheet_id: int, row_index: int) -> Dict[str, Any]:
        """
        Delete a specific row from a Google Sheet.

        Args:
            spreadsheet_id: The ID of the spreadsheet.
            sheet_id: The numeric ID of the sheet (tab), usually 0 for first sheet.
            row_index: Zero-based row index to delete.

        Returns:
            Response from the API.
        """
        request_body = {
            'requests': [{
                'deleteDimension': {
                    'range': {
                        'sheetId': sheet_id,
                        'dimension': 'ROWS',
                        'startIndex': row_index,
                        'endIndex': row_index + 1,
                    }
                }
            }]
        }
        result = self.sheets_service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body=request_body
        ).execute()
        return result

    def get_spreadsheet_metadata(self, spreadsheet_id: str) -> Dict[str, Any]:
        """Get metadata about a spreadsheet including sheet names."""
        result = self.sheets_service.spreadsheets().get(
            spreadsheetId=spreadsheet_id
        ).execute()
        return result

    def get_sheet_id_by_name(self, spreadsheet_id: str, sheet_name: str) -> int:
        """
        Get the numeric sheet ID for a sheet by its name.

        Args:
            spreadsheet_id: The ID of the spreadsheet.
            sheet_name: The name of the sheet (tab).

        Returns:
            The numeric sheet ID.

        Raises:
            ValueError: If no sheet with the given name is found.
        """
        metadata = self.get_spreadsheet_metadata(spreadsheet_id)
        for sheet in metadata.get('sheets', []):
            props = sheet.get('properties', {})
            if props.get('title') == sheet_name:
                return props.get('sheetId')
        raise ValueError(f"No sheet named '{sheet_name}' found in spreadsheet")


class GoogleDocsConnector:
    """Manages connection to Google Docs API."""

    def __init__(self, credentials_path: Optional[str] = None):
        self.credentials = _load_credentials(credentials_path)
        self.docs_service = build('docs', 'v1', credentials=self.credentials)

    def read_doc(self, document_id: str) -> str:
        """Read all text content from a Google Doc."""
        doc = self.docs_service.documents().get(documentId=document_id).execute()
        text_parts = []
        for element in doc.get('body', {}).get('content', []):
            paragraph = element.get('paragraph')
            if paragraph:
                for run in paragraph.get('elements', []):
                    text_run = run.get('textRun')
                    if text_run:
                        text_parts.append(text_run.get('content', ''))
        return ''.join(text_parts)

    def write_doc(self, document_id: str, content: str) -> Dict[str, Any]:
        """Replace all content in a Google Doc with new text."""
        doc = self.docs_service.documents().get(documentId=document_id).execute()
        body_content = doc.get('body', {}).get('content', [])

        end_index = 1
        for element in body_content:
            if 'endIndex' in element:
                end_index = element['endIndex']

        requests = []
        if end_index > 2:
            requests.append({
                'deleteContentRange': {
                    'range': {
                        'startIndex': 1,
                        'endIndex': end_index - 1,
                    }
                }
            })

        requests.append({
            'insertText': {
                'location': {'index': 1},
                'text': content,
            }
        })

        return self.docs_service.documents().batchUpdate(
            documentId=document_id,
            body={'requests': requests}
        ).execute()


# Global connector instances (initialized on demand)
_connector = None
_docs_connector = None


def get_sheets_connector(credentials_path: Optional[str] = None) -> GoogleSheetsConnector:
    """Get or create a Google Sheets connector instance."""
    global _connector
    if _connector is None:
        _connector = GoogleSheetsConnector(credentials_path)
    return _connector


def get_docs_connector(credentials_path: Optional[str] = None) -> GoogleDocsConnector:
    """Get or create a Google Docs connector instance."""
    global _docs_connector
    if _docs_connector is None:
        _docs_connector = GoogleDocsConnector(credentials_path)
    return _docs_connector

import logging
import os
import json
import azure.functions as func
from azure.identity import DefaultAzureCredential
from azure.cosmos import CosmosClient, exceptions
from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.ai.documentintelligence.models import AnalyzeResult
from datetime import datetime
import requests


def download_blob_content(blob_url: str, credential) -> bytes:
    """
    Download blob content from Azure Storage using the blob URL and Managed Identity.
    
    Args:
        blob_url: The full URL to the blob
        credential: Azure credential for authentication
        
    Returns:
        The blob content as bytes
    """
    try:
        # Get access token for Storage
        token = credential.get_token("https://storage.azure.com/.default")
        
        # Download blob with authentication
        headers = {
            'Authorization': f'Bearer {token.token}',
            'x-ms-version': '2021-08-06'
        }
        
        response = requests.get(blob_url, headers=headers)
        response.raise_for_status()
        
        return response.content
    except Exception as e:
        logging.error(f"Error downloading blob from {blob_url}: {str(e)}")
        raise


def analyze_receipt_with_document_intelligence(
    document_intelligence_endpoint: str,
    credential,
    blob_content: bytes
) -> dict:
    """
    Analyze a receipt document using Azure Document Intelligence.
    
    Args:
        document_intelligence_endpoint: The Document Intelligence service endpoint
        credential: Azure credential for authentication
        blob_content: The document content as bytes
        
    Returns:
        A dictionary with extracted fields: purchase_date, merchant_name, total_amount
    """
    try:
        # Create Document Intelligence client
        client = DocumentIntelligenceClient(
            endpoint=document_intelligence_endpoint,
            credential=credential
        )
        
        # Analyze the document using the prebuilt receipt model
        poller = client.begin_analyze_document(
            model_id="prebuilt-receipt",
            analyze_request=blob_content,
            content_type="application/octet-stream"
        )
        
        result: AnalyzeResult = poller.result()
        
        # Extract receipt fields
        extracted_data = {
            'purchase_date': None,
            'merchant_name': None,
            'total_amount': None
        }
        
        if result.documents:
            for document in result.documents:
                if document.fields:
                    # Extract transaction date
                    if 'TransactionDate' in document.fields and document.fields['TransactionDate'].value:
                        extracted_data['purchase_date'] = str(document.fields['TransactionDate'].value)
                    
                    # Extract merchant name
                    if 'MerchantName' in document.fields and document.fields['MerchantName'].value:
                        extracted_data['merchant_name'] = document.fields['MerchantName'].value
                    
                    # Extract total amount
                    if 'Total' in document.fields and document.fields['Total'].value:
                        extracted_data['total_amount'] = float(document.fields['Total'].value)
        
        logging.info(f"Extracted data from receipt: {extracted_data}")
        return extracted_data
        
    except Exception as e:
        logging.error(f"Error analyzing document with Document Intelligence: {str(e)}")
        # Return empty values on error
        return {
            'purchase_date': None,
            'merchant_name': None,
            'total_amount': None
        }


def main(event: func.EventGridEvent):
    """
    Azure Function triggered by Event Grid for blob storage events.
    Downloads the blob, analyzes it with Document Intelligence to extract receipt data,
    and writes the metadata and extracted information to CosmosDB using Managed Identity.
    
    Args:
        event: The Event Grid event that triggered the function
    """
    # Parse the Event Grid event
    event_data = event.get_json()
    
    # Extract blob information from the event
    blob_url = event_data.get('url', '')
    blob_size = event_data.get('contentLength', 0)
    
    logging.info(f"Python Event Grid trigger function processed event \n"
                 f"Event Type: {event.event_type}\n"
                 f"Subject: {event.subject}\n"
                 f"Blob URL: {blob_url}\n"
                 f"Blob Size: {blob_size} bytes")
    
    try:
        # Extract blob path from the subject (format: /blobServices/default/containers/{container}/blobs/{path})
        subject_parts = event.subject.split('/blobs/')
        if len(subject_parts) < 2:
            raise ValueError(f"Invalid subject format: {event.subject}")
        
        blob_path = subject_parts[1]
        blob_name = blob_path.split('/')[-1]
        
        # Get configuration from environment variables
        cosmos_endpoint = os.environ.get('CosmosDBEndpoint')
        database_name = os.environ.get('CosmosDBDatabase', 'serverless-demo')
        document_intelligence_endpoint = os.environ.get('DocumentIntelligenceEndpoint')
        container_name = 'files'
        
        if not cosmos_endpoint:
            raise ValueError("CosmosDBEndpoint environment variable is not set")
        
        # Authenticate using Managed Identity
        credential = DefaultAzureCredential()
        
        # Initialize extracted data with None values
        extracted_data = {
            'purchase_date': None,
            'merchant_name': None,
            'total_amount': None
        }
        
        # If Document Intelligence endpoint is configured, analyze the document
        if document_intelligence_endpoint:
            try:
                logging.info("Downloading blob content for Document Intelligence analysis")
                blob_content = download_blob_content(blob_url, credential)
                
                logging.info("Analyzing receipt with Document Intelligence")
                extracted_data = analyze_receipt_with_document_intelligence(
                    document_intelligence_endpoint,
                    credential,
                    blob_content
                )
            except Exception as e:
                logging.warning(f"Failed to analyze document with Document Intelligence: {str(e)}. "
                              f"Continuing with null values for extracted fields.")
        else:
            logging.info("DocumentIntelligenceEndpoint not configured. Skipping receipt analysis.")
        
        # Create CosmosDB client
        client = CosmosClient(url=cosmos_endpoint, credential=credential)
        
        # Get database and container
        database = client.get_database_client(database_name)
        container = database.get_container_client(container_name)
        
        # Create document to insert
        document = {
            'id': blob_name,
            'fileName': blob_name,
            'blobPath': blob_path,
            'blobUrl': blob_url,
            'blobSize': blob_size,
            'timestamp': datetime.utcnow().isoformat(),
            'eventType': event.event_type,
            'purchaseDate': extracted_data['purchase_date'],
            'merchantName': extracted_data['merchant_name'],
            'totalAmount': extracted_data['total_amount']
        }
        
        # Insert or update the document
        container.upsert_item(document)
        
        logging.info(f"Successfully wrote file '{blob_name}' to CosmosDB collection '{container_name}' "
                    f"with extracted data: {extracted_data}")
        
    except exceptions.CosmosHttpResponseError as e:
        logging.error(f"CosmosDB error: {e.status_code} - {e.message}")
        raise
    except Exception as e:
        logging.error(f"Error processing Event Grid event: {str(e)}")
        raise

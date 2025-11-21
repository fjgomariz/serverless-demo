import logging
import os
import azure.functions as func
from azure.identity import DefaultAzureCredential
from azure.cosmos import CosmosClient, exceptions
from azure.ai.formrecognizer import DocumentAnalysisClient
from azure.core.credentials import TokenCredential
from datetime import datetime, date


def analyze_receipt(blob_url: str, document_intelligence_endpoint: str, credential: TokenCredential) -> dict:
    """
    Analyze a receipt using Azure Document Intelligence.
    
    Args:
        blob_url: URL of the blob to analyze
        document_intelligence_endpoint: Endpoint for Document Intelligence service
        credential: Azure credential for authentication
    
    Returns:
        Dictionary with extracted fields: purchaseDate, supermarket, totalAmount
    """
    result = {
        'purchaseDate': None,
        'supermarket': None,
        'totalAmount': None
    }

    try:
        # Create Document Analysis client with Managed Identity
        document_client = DocumentAnalysisClient(
            endpoint=document_intelligence_endpoint,
            credential=credential
        )

        # Analyze the receipt using the prebuilt receipt model
        poller = document_client.begin_analyze_document_from_url(
            "prebuilt-receipt", blob_url
        )
        receipts = poller.result()

        # Extract information from the first receipt found
        if receipts.documents:
            receipt = receipts.documents[0]
            fields = receipt.fields

            # Extract merchant name (supermarket)
            if fields.get("MerchantName"):
                result['supermarket'] = fields["MerchantName"].value

            # Extract transaction date (purchase date)
            if fields.get("TransactionDate"):
                transaction_date = fields["TransactionDate"].value
                if isinstance(transaction_date, (date, datetime)):
                    result['purchaseDate'] = transaction_date.isoformat()
                else:
                    result['purchaseDate'] = str(transaction_date)

            # Extract total amount
            if fields.get("Total"):
                result['totalAmount'] = fields["Total"].value

            logging.info(f"Extracted receipt data: {result}")
        else:
            logging.warning("No receipt documents found in the analysis result")

    except Exception as e:
        logging.error(f"Error analyzing receipt with Document Intelligence for blob {blob_url}: {str(e)}")
        # Don't raise the exception - we still want to save the blob metadata even if analysis fails

    return result


def main(event: func.EventGridEvent):
    """
    Azure Function triggered by Event Grid for blob storage events.
    Writes the blob filename to CosmosDB using Managed Identity.
    
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

        # Analyze receipt using Document Intelligence if endpoint is configured
        receipt_data = {}
        if document_intelligence_endpoint:
            logging.info("Analyzing receipt with Document Intelligence")
            receipt_data = analyze_receipt(blob_url, document_intelligence_endpoint, credential)
        else:
            logging.info("DocumentIntelligenceEndpoint not configured, skipping receipt analysis")

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
            'eventType': event.event_type
        }

        # Add receipt data if available
        if receipt_data.get('purchaseDate'):
            document['purchaseDate'] = receipt_data['purchaseDate']
        if receipt_data.get('supermarket'):
            document['supermarket'] = receipt_data['supermarket']
        if receipt_data.get('totalAmount'):
            document['totalAmount'] = receipt_data['totalAmount']

        # Insert or update the document
        container.upsert_item(document)

        logging.info(f"Successfully wrote file '{blob_name}' to CosmosDB collection '{container_name}'")

    except exceptions.CosmosHttpResponseError as e:
        logging.error(f"CosmosDB error: {e.status_code} - {e.message}")
        raise
    except Exception as e:
        logging.error(f"Error processing Event Grid event: {str(e)}")
        raise

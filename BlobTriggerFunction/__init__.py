import logging
import os
import json
import azure.functions as func
from azure.identity import DefaultAzureCredential
from azure.cosmos import CosmosClient, exceptions
from datetime import datetime


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
        container_name = 'files'
        
        if not cosmos_endpoint:
            raise ValueError("CosmosDBEndpoint environment variable is not set")
        
        # Authenticate using Managed Identity
        credential = DefaultAzureCredential()
        
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
        
        # Insert or update the document
        container.upsert_item(document)
        
        logging.info(f"Successfully wrote file '{blob_name}' to CosmosDB collection '{container_name}'")
        
    except exceptions.CosmosHttpResponseError as e:
        logging.error(f"CosmosDB error: {e.status_code} - {e.message}")
        raise
    except Exception as e:
        logging.error(f"Error processing Event Grid event: {str(e)}")
        raise

import logging
import os
import azure.functions as func
from azure.identity import DefaultAzureCredential
from azure.cosmos import CosmosClient, exceptions
from datetime import datetime


def main(myblob: func.InputStream):
    """
    Azure Function triggered by blob storage.
    Writes the blob filename to CosmosDB using Managed Identity.
    
    Args:
        myblob: The blob that triggered the function
    """
    logging.info(f"Python blob trigger function processed blob \n"
                 f"Name: {myblob.name}\n"
                 f"Blob Size: {myblob.length} bytes")
    
    try:
        # Extract just the filename from the full blob path
        blob_name = myblob.name.split('/')[-1]
        
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
            'blobPath': myblob.name,
            'blobSize': myblob.length,
            'timestamp': datetime.utcnow().isoformat()
        }
        
        # Insert or update the document
        container.upsert_item(document)
        
        logging.info(f"Successfully wrote file '{blob_name}' to CosmosDB collection '{container_name}'")
        
    except exceptions.CosmosHttpResponseError as e:
        logging.error(f"CosmosDB error: {e.status_code} - {e.message}")
        raise
    except Exception as e:
        logging.error(f"Error processing blob: {str(e)}")
        raise

# serverless-demo

Azure Function with Event Grid Trigger for Blob Storage and CosmosDB Integration

## Overview

This is a Python Azure Function that:
- Triggers automatically when a new file is uploaded to a specific blob storage container via Event Grid
- Reads the blob file information from the Event Grid event
- Downloads the blob and analyzes it with Azure Document Intelligence to extract receipt information
- Writes the file metadata and extracted receipt data to a CosmosDB collection named `files`
- Uses Managed Identities for secure authentication to CosmosDB, Storage, and Document Intelligence
- Compatible with Azure Functions Flex Consumption plan

## Architecture

- **Trigger**: Event Grid (for Blob Storage events on container: `files`)
- **Processing**: Azure Document Intelligence (for receipt data extraction)
- **Target**: CosmosDB (database: `serverless-demo`, collection: `files`)
- **Authentication**: Azure Managed Identity (no connection strings required)

## Prerequisites

- Azure subscription
- Azure Function App (Python 3.9+) - **Flex Consumption plan supported**
- Azure Storage Account
- Azure Event Grid System Topic for the Storage Account
- Azure Document Intelligence resource (for receipt analysis)
- Azure CosmosDB account with:
  - Database: `serverless-demo`
  - Container: `files` (with partition key `/id`)
- Managed Identity enabled on the Function App with:
  - Cosmos DB Built-in Data Contributor role on the CosmosDB account
  - Storage Blob Data Reader role on the Storage Account (for blob downloads)
  - Cognitive Services User role on the Document Intelligence resource

## Project Structure

```
.
├── host.json                          # Function app configuration
├── requirements.txt                   # Python dependencies
├── local.settings.json.example        # Example local settings
└── BlobTriggerFunction/
    ├── __init__.py                    # Function implementation
    └── function.json                  # Function bindings
```

## Configuration

### Application Settings

Set the following application settings in your Azure Function App:

| Setting | Description | Example |
|---------|-------------|---------|
| `CosmosDBEndpoint` | CosmosDB account endpoint | `https://mycosmosdb.documents.azure.com:443/` |
| `CosmosDBDatabase` | CosmosDB database name | `serverless-demo` |
| `DocumentIntelligenceEndpoint` | Document Intelligence service endpoint (optional) | `https://mydocint.cognitiveservices.azure.com/` |

**Note**: With Event Grid trigger, you no longer need `BlobStorageConnection` settings. The `DocumentIntelligenceEndpoint` is optional - if not provided, receipt analysis will be skipped and only basic file metadata will be stored.

### Managed Identity Setup

1. **Enable System-assigned Managed Identity** on your Function App:
   ```bash
   az functionapp identity assign --name <function-app-name> --resource-group <resource-group>
   ```

2. **Grant CosmosDB Access**:
   ```bash
   az cosmosdb sql role assignment create \
     --account-name <cosmosdb-account-name> \
     --resource-group <resource-group> \
     --scope "/" \
     --principal-id <managed-identity-principal-id> \
     --role-definition-id 00000000-0000-0000-0000-000000000002
   ```

3. **Grant Storage Access** (required for blob downloads):
   ```bash
   az role assignment create \
     --role "Storage Blob Data Reader" \
     --assignee <managed-identity-principal-id> \
     --scope /subscriptions/<subscription-id>/resourceGroups/<resource-group>/providers/Microsoft.Storage/storageAccounts/<storage-account-name>
   ```

4. **Grant Document Intelligence Access**:
   ```bash
   az role assignment create \
     --role "Cognitive Services User" \
     --assignee <managed-identity-principal-id> \
     --scope /subscriptions/<subscription-id>/resourceGroups/<resource-group>/providers/Microsoft.CognitiveServices/accounts/<document-intelligence-account-name>
   ```

### Event Grid Setup

Create an Event Grid subscription to trigger the function on blob creation:

1. **Create Event Grid System Topic for Storage Account**:
   ```bash
   az eventgrid system-topic create \
     --name <topic-name> \
     --resource-group <resource-group> \
     --source /subscriptions/<subscription-id>/resourceGroups/<resource-group>/providers/Microsoft.Storage/storageAccounts/<storage-account-name> \
     --topic-type Microsoft.Storage.StorageAccounts \
     --location <location>
   ```

2. **Create Event Grid Subscription**:
   ```bash
   az eventgrid event-subscription create \
     --name <subscription-name> \
     --source-resource-id /subscriptions/<subscription-id>/resourceGroups/<resource-group>/providers/Microsoft.Storage/storageAccounts/<storage-account-name> \
     --endpoint /subscriptions/<subscription-id>/resourceGroups/<resource-group>/providers/Microsoft.Web/sites/<function-app-name>/functions/BlobTriggerFunction \
     --endpoint-type azurefunction \
     --included-event-types Microsoft.Storage.BlobCreated \
     --subject-begins-with /blobServices/default/containers/files/
   ```

## Local Development

1. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Create `local.settings.json`**:
   ```json
   {
     "IsEncrypted": false,
     "Values": {
       "AzureWebJobsStorage": "UseDevelopmentStorage=true",
       "FUNCTIONS_WORKER_RUNTIME": "python",
       "CosmosDBEndpoint": "https://yourcosmosdb.documents.azure.com:443/",
       "CosmosDBDatabase": "serverless-demo",
       "DocumentIntelligenceEndpoint": "https://yourdocint.cognitiveservices.azure.com/"
     }
   }
   ```

3. **Run locally**:
   ```bash
   func start
   ```

   **Note**: For local testing with Event Grid, you can use the Azure Event Grid CLI or ngrok to tunnel events to your local function. Alternatively, use the Event Grid emulator for local development.

## Deployment

Deploy using Azure Functions Core Tools:

```bash
func azure functionapp publish <function-app-name>
```

Or use continuous deployment by linking this repository with Azure Portal.

## Function Behavior

When a new blob is added to the `files` container:
1. The blob creation triggers an Event Grid event
2. The Event Grid subscription delivers the event to the Azure Function
3. The function extracts blob information from the event data
4. If Document Intelligence is configured:
   - Downloads the blob content using Managed Identity
   - Analyzes the receipt using Document Intelligence prebuilt-receipt model
   - Extracts purchase date, merchant name, and total amount
5. It connects to CosmosDB using Managed Identity
6. It creates/updates a document in the `files` collection with:
   - `id`: The blob filename
   - `fileName`: The blob filename
   - `blobPath`: Relative path to the blob within the container
   - `blobUrl`: Full URL to the blob
   - `blobSize`: Size in bytes
   - `timestamp`: UTC timestamp when processed
   - `eventType`: The Event Grid event type (e.g., Microsoft.Storage.BlobCreated)
   - `purchaseDate`: Extracted purchase date from receipt (null if not available)
   - `merchantName`: Extracted merchant/supermarket name from receipt (null if not available)
   - `totalAmount`: Extracted total amount from receipt (null if not available)

## Security

This implementation uses Azure Managed Identity for authentication:
- **No connection strings** stored in code or configuration
- **Automatic credential rotation** by Azure
- **Least privilege access** through role assignments
- **Secure by default** - follows Azure best practices
- **Event Grid security** - uses Azure's built-in authentication and authorization

## Monitoring

View logs and metrics in:
- Azure Portal > Function App > Monitor
- Application Insights (if configured)

## Troubleshooting

### Common Issues

1. **Permission denied errors**: Verify Managed Identity has the correct role assignments for CosmosDB
2. **Connection errors**: Check that endpoint URLs are correct in application settings
3. **Function not triggering**: 
   - Verify the Event Grid subscription is created and active
   - Check the subject filter matches your container path (`/blobServices/default/containers/files/`)
   - Ensure the event type filter includes `Microsoft.Storage.BlobCreated`
   - Review Event Grid subscription delivery status in Azure Portal
4. **Event Grid subscription issues**: Use Azure Portal to verify the subscription status and check for failed deliveries

## Flex Consumption Plan Benefits

With Event Grid triggers, this function is fully compatible with Azure Functions Flex Consumption plan, which offers:
- **Better scalability**: Event-driven scaling optimized for Event Grid
- **Cost efficiency**: Pay only for actual execution time
- **Faster cold starts**: Improved performance for event-driven workloads
- **No blob polling**: Events are delivered directly, reducing latency


# serverless-demo

Azure Function with Blob Storage Trigger and CosmosDB Integration

## Overview

This is a Python Azure Function that:
- Triggers automatically when a new file is uploaded to a specific blob storage container
- Reads the blob file name
- Writes the file metadata to a CosmosDB collection named `files`
- Uses Managed Identities for secure authentication to both Blob Storage and CosmosDB

## Architecture

- **Trigger**: Blob Storage (container: `files`)
- **Target**: CosmosDB (database: `serverless-demo`, collection: `files`)
- **Authentication**: Azure Managed Identity (no connection strings required)

## Prerequisites

- Azure subscription
- Azure Function App (Python 3.9+)
- Azure Storage Account
- Azure CosmosDB account with:
  - Database: `serverless-demo`
  - Container: `files` (with partition key `/id`)
- Managed Identity enabled on the Function App with:
  - Storage Blob Data Reader role on the Storage Account
  - Cosmos DB Built-in Data Contributor role on the CosmosDB account

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
| `BlobStorageConnection__blobServiceUri` | Storage account blob service URI | `https://mystorageaccount.blob.core.windows.net` |
| `BlobStorageConnection__credential` | Authentication method | `managedidentity` |
| `CosmosDBEndpoint` | CosmosDB account endpoint | `https://mycosmosdb.documents.azure.com:443/` |
| `CosmosDBDatabase` | CosmosDB database name | `serverless-demo` |

### Managed Identity Setup

1. **Enable System-assigned Managed Identity** on your Function App:
   ```bash
   az functionapp identity assign --name <function-app-name> --resource-group <resource-group>
   ```

2. **Grant Storage Access**:
   ```bash
   az role assignment create \
     --assignee <managed-identity-principal-id> \
     --role "Storage Blob Data Reader" \
     --scope /subscriptions/<subscription-id>/resourceGroups/<resource-group>/providers/Microsoft.Storage/storageAccounts/<storage-account-name>
   ```

3. **Grant CosmosDB Access**:
   ```bash
   az cosmosdb sql role assignment create \
     --account-name <cosmosdb-account-name> \
     --resource-group <resource-group> \
     --scope "/" \
     --principal-id <managed-identity-principal-id> \
     --role-definition-id 00000000-0000-0000-0000-000000000002
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
       "BlobStorageConnection__blobServiceUri": "https://yourstorageaccount.blob.core.windows.net",
       "BlobStorageConnection__credential": "managedidentity",
       "CosmosDBEndpoint": "https://yourcosmosdb.documents.azure.com:443/",
       "CosmosDBDatabase": "serverless-demo"
     }
   }
   ```

3. **Run locally**:
   ```bash
   func start
   ```

## Deployment

Deploy using Azure Functions Core Tools:

```bash
func azure functionapp publish <function-app-name>
```

Or use continuous deployment by linking this repository with Azure Portal.

## Function Behavior

When a new blob is added to the `files` container:
1. The function is triggered automatically
2. It extracts the blob name and metadata
3. It connects to CosmosDB using Managed Identity
4. It creates/updates a document in the `files` collection with:
   - `id`: The blob filename
   - `fileName`: The blob filename
   - `blobPath`: Full path to the blob
   - `blobSize`: Size in bytes
   - `timestamp`: UTC timestamp when processed

## Security

This implementation uses Azure Managed Identity for authentication:
- **No connection strings** stored in code or configuration
- **Automatic credential rotation** by Azure
- **Least privilege access** through role assignments
- **Secure by default** - follows Azure best practices

## Monitoring

View logs and metrics in:
- Azure Portal > Function App > Monitor
- Application Insights (if configured)

## Troubleshooting

### Common Issues

1. **Permission denied errors**: Verify Managed Identity has the correct role assignments
2. **Connection errors**: Check that endpoint URLs are correct in application settings
3. **Function not triggering**: Verify the blob container name matches the path in `function.json`


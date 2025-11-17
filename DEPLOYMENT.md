# Deployment Guide

## Quick Start

### 1. Prerequisites Setup

Before deploying, ensure you have:
- Azure CLI installed
- Azure Function Core Tools installed
- An Azure subscription

### 2. Create Azure Resources

```bash
# Set variables
RESOURCE_GROUP="serverless-demo-rg"
LOCATION="eastus"
STORAGE_ACCOUNT="serverlessdemostore"
FUNCTION_APP="serverless-demo-func"
COSMOSDB_ACCOUNT="serverless-demo-cosmos"

# Create resource group
az group create --name $RESOURCE_GROUP --location $LOCATION

# Create storage account
az storage account create \
  --name $STORAGE_ACCOUNT \
  --resource-group $RESOURCE_GROUP \
  --location $LOCATION \
  --sku Standard_LRS

# Create blob container
az storage container create \
  --name files \
  --account-name $STORAGE_ACCOUNT

# Create CosmosDB account
az cosmosdb create \
  --name $COSMOSDB_ACCOUNT \
  --resource-group $RESOURCE_GROUP \
  --locations regionName=$LOCATION

# Create database and container
az cosmosdb sql database create \
  --account-name $COSMOSDB_ACCOUNT \
  --resource-group $RESOURCE_GROUP \
  --name serverless-demo

az cosmosdb sql container create \
  --account-name $COSMOSDB_ACCOUNT \
  --resource-group $RESOURCE_GROUP \
  --database-name serverless-demo \
  --name files \
  --partition-key-path "/id"

# Create Function App (Flex Consumption or Consumption plan)
# For Flex Consumption (recommended):
az functionapp create \
  --resource-group $RESOURCE_GROUP \
  --name $FUNCTION_APP \
  --storage-account $STORAGE_ACCOUNT \
  --runtime python \
  --runtime-version 3.11 \
  --functions-version 4 \
  --os-type Linux \
  --flexconsumption-location $LOCATION

# OR for standard Consumption plan:
# az functionapp create \
#   --resource-group $RESOURCE_GROUP \
#   --consumption-plan-location $LOCATION \
#   --runtime python \
#   --runtime-version 3.9 \
#   --functions-version 4 \
#   --name $FUNCTION_APP \
#   --storage-account $STORAGE_ACCOUNT \
#   --os-type Linux
```

### 3. Enable Managed Identity

```bash
# Enable system-assigned identity
az functionapp identity assign \
  --name $FUNCTION_APP \
  --resource-group $RESOURCE_GROUP

# Get the principal ID
PRINCIPAL_ID=$(az functionapp identity show \
  --name $FUNCTION_APP \
  --resource-group $RESOURCE_GROUP \
  --query principalId -o tsv)
```

### 4. Assign Permissions

```bash
# Grant CosmosDB access (built-in data contributor role)
az cosmosdb sql role assignment create \
  --account-name $COSMOSDB_ACCOUNT \
  --resource-group $RESOURCE_GROUP \
  --scope "/" \
  --principal-id $PRINCIPAL_ID \
  --role-definition-id 00000000-0000-0000-0000-000000000002
```

**Note**: With Event Grid trigger, you no longer need to assign Storage Blob Data Reader role to the Function App's Managed Identity.

### 5. Configure Application Settings

```bash
# Get CosmosDB endpoint
COSMOS_ENDPOINT=$(az cosmosdb show \
  --name $COSMOSDB_ACCOUNT \
  --resource-group $RESOURCE_GROUP \
  --query documentEndpoint -o tsv)

# Configure Function App settings
az functionapp config appsettings set \
  --name $FUNCTION_APP \
  --resource-group $RESOURCE_GROUP \
  --settings \
    "CosmosDBEndpoint=$COSMOS_ENDPOINT" \
    "CosmosDBDatabase=serverless-demo"
```

### 6. Create Event Grid Subscription

Create an Event Grid subscription to send blob storage events to your function:

```bash
# Get Function App resource ID
FUNCTION_RESOURCE_ID=$(az functionapp show \
  --name $FUNCTION_APP \
  --resource-group $RESOURCE_GROUP \
  --query id -o tsv)

# Get Storage Account resource ID
STORAGE_RESOURCE_ID=$(az storage account show \
  --name $STORAGE_ACCOUNT \
  --resource-group $RESOURCE_GROUP \
  --query id -o tsv)

# Create Event Grid subscription
az eventgrid event-subscription create \
  --name blob-created-subscription \
  --source-resource-id $STORAGE_RESOURCE_ID \
  --endpoint-type azurefunction \
  --endpoint "${FUNCTION_RESOURCE_ID}/functions/BlobTriggerFunction" \
  --included-event-types Microsoft.Storage.BlobCreated \
  --subject-begins-with /blobServices/default/containers/files/
```

**Important**: The Event Grid subscription filters events to only trigger on blob creation in the `files` container.

### 7. Deploy the Function

```bash
# Deploy using Azure Functions Core Tools
func azure functionapp publish $FUNCTION_APP
```

## Testing

Upload a test file to verify the function works:

```bash
# Upload a test file
echo "test content" > test.txt
az storage blob upload \
  --account-name $STORAGE_ACCOUNT \
  --container-name files \
  --name test.txt \
  --file test.txt
```

The Event Grid event should trigger the function automatically. Check the CosmosDB collection for the new document:

```bash
az cosmosdb sql container query \
  --account-name $COSMOSDB_ACCOUNT \
  --resource-group $RESOURCE_GROUP \
  --database-name serverless-demo \
  --name files \
  --query-text "SELECT * FROM c"
```

## Monitoring

View function execution logs:

```bash
# Stream logs
func azure functionapp logstream $FUNCTION_APP

# Or view in Azure Portal
# Navigate to: Function App > Functions > BlobTriggerFunction > Monitor
```

Check Event Grid subscription delivery status:

```bash
# View Event Grid metrics in Azure Portal
# Navigate to: Storage Account > Events > Event Subscriptions > blob-created-subscription
```

## Troubleshooting

If the function doesn't trigger:
1. Check Managed Identity is enabled on the Function App
2. Verify CosmosDB role assignment is correct
3. Check application settings (CosmosDBEndpoint, CosmosDBDatabase)
4. **Verify Event Grid subscription exists and is active**
5. **Check Event Grid subscription subject filter** (`/blobServices/default/containers/files/`)
6. **Ensure event type filter includes** `Microsoft.Storage.BlobCreated`
7. Review function logs for errors
8. Check Event Grid delivery metrics in Azure Portal
9. Ensure the blob is uploaded to the `files` container

### Event Grid Subscription Validation

Verify the Event Grid subscription is working:

```bash
# List Event Grid subscriptions for the storage account
az eventgrid event-subscription list \
  --source-resource-id $STORAGE_RESOURCE_ID \
  --query "[].{name:name, endpoint:destination.endpointType, status:provisioningState}"
```

## Cleanup

To delete all resources:

```bash
az group delete --name $RESOURCE_GROUP --yes --no-wait
```

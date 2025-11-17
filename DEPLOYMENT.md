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

# Create Function App
az functionapp create \
  --resource-group $RESOURCE_GROUP \
  --consumption-plan-location $LOCATION \
  --runtime python \
  --runtime-version 3.9 \
  --functions-version 4 \
  --name $FUNCTION_APP \
  --storage-account $STORAGE_ACCOUNT \
  --os-type Linux
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
# Grant Storage Blob Data Reader role
az role assignment create \
  --assignee $PRINCIPAL_ID \
  --role "Storage Blob Data Reader" \
  --scope /subscriptions/$(az account show --query id -o tsv)/resourceGroups/$RESOURCE_GROUP/providers/Microsoft.Storage/storageAccounts/$STORAGE_ACCOUNT

# Grant CosmosDB access (built-in data contributor role)
az cosmosdb sql role assignment create \
  --account-name $COSMOSDB_ACCOUNT \
  --resource-group $RESOURCE_GROUP \
  --scope "/" \
  --principal-id $PRINCIPAL_ID \
  --role-definition-id 00000000-0000-0000-0000-000000000002
```

### 5. Configure Application Settings

```bash
# Get storage account URL
STORAGE_URL=$(az storage account show \
  --name $STORAGE_ACCOUNT \
  --resource-group $RESOURCE_GROUP \
  --query primaryEndpoints.blob -o tsv)

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
    "BlobStorageConnection__blobServiceUri=$STORAGE_URL" \
    "BlobStorageConnection__credential=managedidentity" \
    "CosmosDBEndpoint=$COSMOS_ENDPOINT" \
    "CosmosDBDatabase=serverless-demo"
```

### 6. Deploy the Function

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

Check the CosmosDB collection for the new document:

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

## Troubleshooting

If the function doesn't trigger:
1. Check Managed Identity is enabled
2. Verify role assignments are correct
3. Check application settings
4. Review function logs for errors
5. Ensure blob container name is 'files'

## Cleanup

To delete all resources:

```bash
az group delete --name $RESOURCE_GROUP --yes --no-wait
```

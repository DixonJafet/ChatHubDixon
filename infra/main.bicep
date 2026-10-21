targetScope = 'subscription'

@description('Azure region for the resource group and backend resources.')
param location string = 'westus3'

@description('Resource group for ChatHubDixon development.')
param resourceGroupName string = 'rg-chathubdixon-dev'

@description('Azure AI Foundry project endpoint.')
param azureAiProjectEndpoint string

@description('Azure AI model deployment name.')
param azureAiModelDeployment string

@description('Azure OpenAI endpoint used for embeddings.')
param azureOpenAiEndpoint string

@description('Azure OpenAI embedding deployment name.')
param azureOpenAiEmbeddingDeployment string

resource resourceGroup 'Microsoft.Resources/resourceGroups@2025-04-01' = {
  name: resourceGroupName
  location: location
  tags: {
    project: 'ChatHubDixon'
    environment: 'dev'
    managedBy: 'Bicep'
  }
}

module backend './resources.bicep' = {
  name: 'chathubdixon-backend'
  scope: resourceGroup
  params: {
    location: location
    azureAiProjectEndpoint: azureAiProjectEndpoint
    azureAiModelDeployment: azureAiModelDeployment
    azureOpenAiEndpoint: azureOpenAiEndpoint
    azureOpenAiEmbeddingDeployment: azureOpenAiEmbeddingDeployment
  }
}

output deployedResourceGroup string = resourceGroup.name
output functionAppName string = backend.outputs.functionAppName
output searchServiceName string = backend.outputs.searchServiceName
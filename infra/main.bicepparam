
using './main.bicep'

param location = 'westus3'
param resourceGroupName = 'rg-chathubdixon-dev'
param azureAiProjectEndpoint = readEnvironmentVariable('AZURE_AI_PROJECT_ENDPOINT')
param azureAiModelDeployment = readEnvironmentVariable('AZURE_AI_MODEL_DEPLOYMENT')
param azureOpenAiEndpoint = readEnvironmentVariable('AZURE_OPENAI_ENDPOINT')
param azureOpenAiEmbeddingDeployment = readEnvironmentVariable('AZURE_OPENAI_EMBEDDING_DEPLOYMENT')

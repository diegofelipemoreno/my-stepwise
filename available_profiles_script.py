import boto3

bedrock = boto3.client('bedrock', region_name='us-east-1')
response = bedrock.list_inference_profiles()

print("--- Perfiles de inferencia disponibles en tu cuenta ---")
for profile in response.get('inferenceProfileSummaries', []):
    if 'anthropic' in profile['inferenceProfileId']:
        print(f"ID: {profile['inferenceProfileId']}")
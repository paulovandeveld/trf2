from datetime import datetime, timedelta
from dotenv import load_dotenv
import json
import re
import os

from azure.storage.blob import BlobServiceClient

load_dotenv()

ACCOUNT_NAME = os.getenv("AZURE_STORAGE_ACCOUNT_NAME")
ACCOUNT_KEY = os.getenv("AZURE_STORAGE_ACCOUNT_KEY")

def check_json_blob(processo_id):
    """Check if a JSON file already exists in Azure Blob Storage."""
    CONNECTION_STRING = (
        f"DefaultEndpointsProtocol=https;"
        f"AccountName={ACCOUNT_NAME};"
        f"AccountKey={ACCOUNT_KEY};"
        f"EndpointSuffix=core.windows.net"
    )
    CONTAINER_NAME = "json-processos"

    data_ref = (datetime.today() - timedelta(days=1)).strftime('%d-%m-%Y')

    try:
        blob_service_client = BlobServiceClient.from_connection_string(CONNECTION_STRING)
        container_client = blob_service_client.get_container_client(CONTAINER_NAME)

        prefix = f"trf2_eproc/{data_ref}/"
        blobs = container_client.list_blobs(name_starts_with=prefix)

        for blob in blobs:
            if re.search(rf"(?:mov_)?{processo_id}\.json$", blob.name):
                return True
    except Exception as e:
        print(f"Erro ao verificar Blob Storage: {e}")

    return False


def save_json_blob(processo_id, full_json):
    """Save JSON to Azure Blob Storage under trf2_eproc/{data_ref}/{processo_id}.json."""
    CONNECTION_STRING = (
        f"DefaultEndpointsProtocol=https;"
        f"AccountName={ACCOUNT_NAME};"
        f"AccountKey={ACCOUNT_KEY};"
        f"EndpointSuffix=core.windows.net"
    )
    CONTAINER_NAME = "json-processos"

    data_ref = (datetime.today() - timedelta(days=1)).strftime('%d-%m-%Y')

    try:
        blob_path = f"trf2_eproc/{data_ref}/{processo_id}.json"

        blob_service_client = BlobServiceClient.from_connection_string(CONNECTION_STRING)
        blob_client = blob_service_client.get_blob_client(container=CONTAINER_NAME, blob=blob_path)

        json_data = json.dumps(full_json, indent=4, ensure_ascii=False)
        blob_client.upload_blob(json_data, overwrite=True)

        print(f"✅ Arquivo salvo no Azure Blob Storage: {blob_path}")
    except Exception as e:
        print(f"❌ Erro ao salvar JSON no Azure Blob Storage: {e}")
        raise


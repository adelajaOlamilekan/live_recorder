"""
PROJECT NAME: Live Recorder Endpoint

"""

from fastapi import FastAPI, UploadFile, HTTPException, Query
from uuid import uuid4
from pydantic import BaseModel
import os
#from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient, BlobClient, ContainerClient, PublicAccess
from azure.core.exceptions import ResourceNotFoundError
from io import BytesIO
import base64
from dotenv import load_dotenv


app = FastAPI()

load_dotenv()

CONTAINER_NAME = os.environ.get("CONTAINER_NAME")
ACCOUNT_URL = os.environ.get("ACCOUNT_URL")
CONNECTION_STRING = os.environ.get("CONNECTION_STRING")

class StartRecordingResponse(BaseModel):
 folder_name: str
 blob_name: str
 status_code: int
 message: str

class AppendBlobResponse(BaseModel):
  status_code: int
  message: str
 
class Chunk(BaseModel):
  data: str
  blob_name: str
  folder_name:str

class VideoResponse(BaseModel):
  status_code: int
  message: str
  url: str

class VideoRequest(BaseModel):
  folder_name: str
  blob_name: str

account_url = ACCOUNT_URL
connection_string = CONNECTION_STRING

# default_credential = DefaultAzureCredential() 

#CREATE RECORDING SESSION FOLDER ID
@app.post("/api/start_recording", status_code=201)
async def start_recording() -> StartRecordingResponse:
 folder_name= str(uuid4())
 blob_name = str(uuid4())
 
 #Create the blob service to interact with the azure account
 blob_service_client = BlobServiceClient.from_connection_string(CONNECTION_STRING)

 #Create container 
 container_client = blob_service_client.create_container(folder_name)

 #Set the anonymous access level to Blob
 container_client.set_container_access_policy(signed_identifiers={}, public_access=PublicAccess.Blob)

 SUCCESS_MESSAGE = "FOLDER CREATED SUCCESSFULLY"
 FAILURE_MESSAGE = "FOLDER FAILED TO BE CREATED"

 if container_client:
  return StartRecordingResponse(folder_name=folder_name, blob_name= blob_name, status_code=201, message=SUCCESS_MESSAGE)
 else:
  return StartRecordingResponse(status_code=422, message=FAILURE_MESSAGE)

@app.post("/api/append_blob", status_code=201)
async def append_blob(file: Chunk):
    
    file_data = base64.b64decode(file.data)


    folder_name = file.folder_name
    blob_name = file.blob_name

    try:
        # Initialize Azure Blob Service Client
        blob_service_client = BlobServiceClient.from_connection_string(CONNECTION_STRING)
        
        container_client = blob_service_client.get_container_client(folder_name)
        
        # Get or create an Append Blob client
        blob_client = container_client.get_blob_client(blob_name)

        if not blob_client.exists():
            blob_client.create_append_blob()
        
        # Read the binary data from the uploaded file and append it to the Append Blob
        blob_client.append_block(file_data, length=len(file_data))
        
        return {"message": "Binary data appended successfully."}
    
    except ResourceNotFoundError:
        raise HTTPException(status_code=404, detail=f"Blob '{blob_name}' not found")
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/stop_recording", status_code=200)
async def stop_recording(file:  VideoRequest):
  folder_name = file.folder_name
  blob_name = file.blob_name
  SUCCESS_MESSAGE = "Video Retrieved Successfully"

  try:
    # Initialize Azure Blob Service Client
    blob_service_client = BlobServiceClient.from_connection_string(CONNECTION_STRING)

    container_client = blob_service_client.get_container_client(folder_name)

    # Get or create an Append Blob client
    blob_client = container_client.get_blob_client(blob_name)

    video_url = blob_client.url

    return VideoResponse(status_code=200, message= SUCCESS_MESSAGE, url = video_url)
  
  except ResourceNotFoundError:
    raise HTTPException(status_code=404, detail=f"Blob '{blob_name}' not found")


if __name__ == "__main__":
 import uvicorn
 uvicorn.run("main:app", reload = True, port=8000)
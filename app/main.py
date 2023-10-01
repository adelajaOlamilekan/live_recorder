"""
PROJECT NAME: Live Recorder Endpoint

"""

from fastapi import FastAPI, HTTPException, Query, Header
from uuid import uuid4
from pydantic import BaseModel
import os
from azure.storage.blob import BlobServiceClient, PublicAccess, ContentSettings
from azure.core.exceptions import ResourceNotFoundError
import base64
from dotenv import load_dotenv
from datetime import datetime


app = FastAPI()

load_dotenv()

# Define the default content type for the container
DEFAULT_CONTENT_TYPE = "video/mp4"

ACCOUNT_URL = os.environ.get("ACCOUNT_URL")
CONNECTION_STRING = os.environ.get("CONNECTION_STRING")

class StartRecordingResponse(BaseModel):
 folder_name: str
 blob_name: str
 status_code: int
 message: str

class StreamRecordingResponse(BaseModel):
  status_code: int
  message: str
 
class Chunk(BaseModel):
  data: str
  blob_name: str
  folder_name: str
  content_type: str


class VideoResponse(BaseModel):
  status_code: int
  message: str
  url: str
  creation_time : str
  modified_time: str
  content_type: str
  title: str

class VideoRequest(BaseModel):
  folder_name: str
  blob_name: str 

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

@app.post("/api/stream_recording", status_code=201)
async def stream_recording(file: Chunk) -> StreamRecordingResponse:
    
    print(file.folder_name, file.blob_name)
    file_data = base64.b64decode(file.data)


    folder_name = file.folder_name
    blob_name = file.blob_name
    content_type = file.content_type

    try:

        # Initialize Azure Blob Service Client
        blob_service_client = BlobServiceClient.from_connection_string(CONNECTION_STRING)
        
        container_client = blob_service_client.get_container_client(folder_name)
        
        # Get or create an Append Blob client
        blob_client = container_client.get_blob_client(blob_name)

        if not blob_client.exists():
          blob_client.create_append_blob()

        # Get the existing blob properties
        properties = blob_client.get_blob_properties()

        # Set the content_type and content_language headers, and populate the remaining headers from the existing properties
        blob_headers = ContentSettings(content_type=content_type,
                                      content_encoding=properties.content_settings.content_encoding,
                                      content_language="en-US",
                                      )
        
        blob_client.set_http_headers(blob_headers)


        # Set the content type to "video/mp4" for the Append Blob
        # blob_client.set_http_headers(content_type=content_type)

        # blob_client.upload_blob(file_data, overwrite=True, content_settings=my_content_settings)


        # Read the binary data from the uploaded file and append it to the Append Blob
        blob_client.append_block(file_data, length=len(file_data))
        
        return StreamRecordingResponse(message= "Binary data appended successfully.", status_code=201)
    
    except ResourceNotFoundError:
        raise HTTPException(status_code=404, detail=f"Blob '{blob_name}' not found")
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/stop_recording", status_code=200)
async def stop_recording(file:  VideoRequest) -> VideoResponse:
  folder_name = file.folder_name
  blob_name = file.blob_name
  SUCCESS_MESSAGE = "Video Retrieved Successfully"

  try:
    # Initialize Azure Blob Service Client
    blob_service_client = BlobServiceClient.from_connection_string(CONNECTION_STRING)

    container_client = blob_service_client.get_container_client(folder_name)

    # Get or create an Append Blob client
    blob_client = container_client.get_blob_client(blob_name)

    # Get the existing blob properties
    properties = blob_client.get_blob_properties()

    # Set the content_type and content_language headers, and populate the remaining headers from the existing properties
    blob_headers = ContentSettings(content_type="video/mp4",
                                  content_encoding=properties.content_settings.content_encoding,
                                  content_language="en-US",
                                  )
    
    blob_client.set_http_headers(blob_headers)

    video_url = blob_client.url
    
    # Get the creation time of the blob (assuming the blob exists)
    creation_time = blob_client.get_blob_properties().creation_time.strftime("%Y-%m-%dT%H:%M:%SZ")
    modified_time = blob_client.get_blob_properties().last_modified.strftime("%Y-%m-%dT%H:%M:%SZ")
    content_type = blob_client.get_blob_properties().content_settings.content_type

    # Format the creation time as a string (e.g., as an ISO 8601 timestamp)
    # creation_time = creation_time.strftime("%Y-%m-%dT%H:%M:%SZ")

    return VideoResponse(status_code=200, message= SUCCESS_MESSAGE, url = video_url, 
                         creation_time=creation_time, modified_time=modified_time, 
                         content_type=content_type, title=blob_name)
  
  except ResourceNotFoundError:
    raise HTTPException(status_code=404, detail=f"Blob '{blob_name}' not found")


if __name__ == "__main__":
 import uvicorn
 uvicorn.run("main:app", reload = True, port=8000)
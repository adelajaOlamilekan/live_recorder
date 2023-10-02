
"""
PROJECT NAME: Live Recorder Backend Endpoint

STORAGE: AZURE CLOUD STORAGE 

"""

from fastapi import FastAPI, HTTPException, Query, Header
from uuid import uuid4
from pydantic import BaseModel, Field
import os
from azure.storage.blob import BlobServiceClient, PublicAccess, ContentSettings
from azure.core.exceptions import ResourceNotFoundError
import base64
from dotenv import load_dotenv
from datetime import datetime
from pathlib import Path
from fastapi.middleware.cors import CORSMiddleware
from moviepy.editor import VideoFileClip
import whisper

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "*",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
  data: str = Field (..., description="Base64-encoded binary data")
  blob_name: str 
  folder_name: str
  content_type: str = Field(..., description="MIME type of the content", example=" 'video/mp4' | 'video/webm' | 'video/mkv'")


class VideoResponse(BaseModel):
  status_code: int
  message: str
  video_url: str
  creation_time : str
  modified_time: str
  content_type: str
  title: str
  transcript_url:str

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
    
    file_data = base64.b64decode(file.data)

    format = file.content_type.replace("video/", "")
    
    folder_name = file.folder_name
    blob_name = file.blob_name
    content_type = format
   
    VIDEO_LOCAL_PATH = f"{blob_name}.{format}"

    print(VIDEO_LOCAL_PATH)

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

        # Read the binary data from the uploaded file and append it to the Append Blob
        blob_client.append_block(file_data, length=len(file_data))

        with open(VIDEO_LOCAL_PATH, "ab") as video_file:
          video_file.write(file_data)
    
        
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
    
    # Get the creation time of the blob (assuming the blob exists)
    creation_time = blob_client.get_blob_properties().creation_time.strftime("%Y-%m-%dT%H:%M:%SZ")
    modified_time = blob_client.get_blob_properties().last_modified.strftime("%Y-%m-%dT%H:%M:%SZ")
    content_type = str(blob_client.get_blob_properties().content_settings.content_type)
    video_url = blob_client.url

    #Transcribing the Video
    video_format = content_type.replace("video/", "")

    video_file_path = f"{blob_name}.{video_format}"

    if isinstance(video_file_path, Path):
      video_file_path = str(video_file_path)

    video_clip = VideoFileClip(video_file_path)

    audio_clip = video_clip.audio

    output_audio_file = f"{blob_name}.mp3"

    audio_clip.write_audiofile(output_audio_file)

    model = whisper.load_model("base")

    result = model.transcribe(output_audio_file)

    transcript_blob_name = f"transcript.txt" 
    transcript_content_type = "text/plain"  

    with open(transcript_blob_name, mode='w') as file:
        transcript = result["text"]
        file.write(transcript)

    video_clip.close()
    audio_clip.close()

    # Get or create a Blob client
    blob_client = container_client.get_blob_client(transcript_blob_name)

    # Create the blob as a block blob (for text files)
    blob_client.upload_blob(open(transcript_blob_name, "rb"), content_settings=ContentSettings(content_type=transcript_content_type))

    
    # Get the URL of the uploaded text file
    transcript_url = blob_client.url

    return VideoResponse(status_code=200, message= SUCCESS_MESSAGE, video_url = video_url, 
                          creation_time=creation_time, modified_time=modified_time, 
                          content_type=content_type, title=blob_name, transcript_url=transcript_url)
  
  except ResourceNotFoundError:
    raise HTTPException(status_code=404, detail=f"Blob '{blob_name}' not found")


if __name__ == "__main__":
 import uvicorn
 uvicorn.run("main:app", reload = True, port=8000)
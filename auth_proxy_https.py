import json
import logging
import os
from typing import Dict, Any, List, Optional
import httpx
from fastapi import FastAPI, Request, Response, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from starlette.background import BackgroundTask
import uvicorn
import ssl

# Configure logging
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Ollama server details
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")

# Path to the API keys file
KEYS_FILE = os.getenv("KEYS_FILE", "keys.json")

# SSL certificate paths
CERT_DIR = "certs"
SSL_KEYFILE = os.path.join(CERT_DIR, "server.key")
SSL_CERTFILE = os.path.join(CERT_DIR, "server.crt")

app = FastAPI(title="Ollama Auth Proxy")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create an async HTTP client
client = httpx.AsyncClient(timeout=None)  # No timeout for streaming responses


def load_api_keys() -> List[str]:
    """Load the authorized API keys from the keys.json file."""
    try:
        with open(KEYS_FILE, 'r') as f:
            keys_data = json.load(f)
            return keys_data.get("keys", [])
    except FileNotFoundError:
        logger.error(f"Keys file {KEYS_FILE} not found. Please create it manually.")
        return []
    except json.JSONDecodeError:
        logger.error(f"Error parsing {KEYS_FILE}. File may be corrupted.")
        return []


async def get_api_key(authorization: Optional[str] = Header(None)) -> Optional[str]:
    """Extract API key from the Authorization header."""
    if authorization and authorization.startswith("Bearer "):
        return authorization[7:]  # Remove 'Bearer ' prefix
    return None


async def validate_api_key(api_key: Optional[str] = Depends(get_api_key)) -> str:
    """Validate the API key and return it if valid."""
    if not api_key:
        raise HTTPException(status_code=401, detail="API key missing")
    
    valid_keys = load_api_keys()
    if api_key not in valid_keys:
        logger.warning(f"Invalid API key attempt: {api_key}")
        raise HTTPException(status_code=401, detail="Invalid API key")
    
    return api_key


def transform_openai_to_ollama(openai_payload: Dict[str, Any]) -> Dict[str, Any]:
    """Transform OpenAI API format to Ollama API format."""
    model = openai_payload.get("model", "llama2")
    
    ollama_payload = {
        "model": model,
        "messages": openai_payload.get("messages", []),
        "stream": openai_payload.get("stream", False),
        "options": {}
    }
    
    # Handle additional parameters
    if "temperature" in openai_payload:
        ollama_payload["options"]["temperature"] = openai_payload["temperature"]
    
    if "max_tokens" in openai_payload:
        ollama_payload["options"]["num_predict"] = openai_payload["max_tokens"]
    
    return ollama_payload


def transform_ollama_to_openai(ollama_response: Dict[str, Any]) -> Dict[str, Any]:
    """Transform Ollama API response to OpenAI API format."""
    return {
        "id": "chatcmpl-" + str(hash(str(ollama_response))),
        "object": "chat.completion",
        "created": 0,  # We don't have this from Ollama
        "model": ollama_response.get("model", "unknown"),
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": ollama_response.get("message", {}).get("content", "")
                },
                "finish_reason": "stop"
            }
        ],
        "usage": {
            "prompt_tokens": 0,  # We don't have this from Ollama
            "completion_tokens": 0,  # We don't have this from Ollama
            "total_tokens": 0  # We don't have this from Ollama
        }
    }


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])
async def proxy_endpoint(
    request: Request,
    path: str,
    api_key: str = Depends(validate_api_key)
) -> Response:
    """Main proxy endpoint that forwards requests to Ollama after authentication."""
    # For OpenAI compatibility, handle the /v1 routes
    if path.startswith('v1/'):
        path = path[3:]  # Remove 'v1/' prefix
    
    # Prepare target URL for Ollama
    target_url = f"{OLLAMA_HOST}/{path}"
    
    # Get request body
    body = await request.body()
    
    # Handle OpenAI to Ollama format conversion for chat completions
    if path == "chat/completions":
        try:
            openai_payload = json.loads(body)
            # Transform payload from OpenAI format to Ollama format
            ollama_payload = transform_openai_to_ollama(openai_payload)
            body = json.dumps(ollama_payload).encode()
            target_url = f"{OLLAMA_HOST}/api/chat"
        except json.JSONDecodeError:
            logger.error("Error parsing OpenAI request format")
    
    # Prepare headers (excluding host and authorization)
    headers = {k: v for k, v in request.headers.items() 
              if k.lower() not in ['host', 'authorization', 'content-length']}
    
    # Forward the request to Ollama
    try:
        logger.info(f"Forwarding request to: {target_url}")
        
        # Make the request to Ollama
        ollama_response = await client.request(
            method=request.method,
            url=target_url,
            headers=headers,
            content=body,
            params=dict(request.query_params),
            follow_redirects=True
        )
        
        # Transform response if it's a chat completion
        if path == "chat/completions":
            try:
                ollama_data = ollama_response.json()
                openai_data = transform_ollama_to_openai(ollama_data)
                response_content = json.dumps(openai_data).encode()
            except Exception as e:
                logger.error(f"Error transforming response: {str(e)}")
                response_content = ollama_response.content
        else:
            response_content = ollama_response.content
        
        # Prepare the response headers
        response_headers = {k: v for k, v in ollama_response.headers.items()
                           if k.lower() not in ['content-encoding', 'content-length', 
                                              'transfer-encoding', 'connection']}
        
        # Create the response
        return Response(
            content=response_content,
            status_code=ollama_response.status_code,
            headers=response_headers,
            media_type=ollama_response.headers.get('content-type')
        )
    
    except Exception as e:
        logger.error(f"Error forwarding request: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error connecting to Ollama server: {str(e)}")


@app.on_event("startup")
async def startup_event():
    """Check if keys.json exists and SSL certificates are present on startup."""
    if not os.path.exists(KEYS_FILE):
        logger.warning(f"Keys file {KEYS_FILE} not found. Please create it manually before using the server.")
        logger.info(f"Example keys.json format: {{\"keys\": [\"sk-myapikey1234567890\", \"sk-testkey9876543210\"]}}")
    else:
        logger.info(f"Using keys file at {KEYS_FILE}")
    
    # Check for SSL certificates
    if not (os.path.exists(SSL_KEYFILE) and os.path.exists(SSL_CERTFILE)):
        logger.warning("SSL certificates not found. Please run generate_certs.py to generate them.")
        logger.info("You can generate certificates by running: python generate_certs.py")
    else:
        logger.info("SSL certificates found and will be used for HTTPS")


@app.on_event("shutdown")
async def shutdown_event():
    """Close the HTTP client on shutdown."""
    await client.aclose()


if __name__ == "__main__":
    ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    ssl_context.load_cert_chain(SSL_CERTFILE, SSL_KEYFILE)
    uvicorn.run("auth_server_https:app", host="0.0.0.0", port=8080, ssl_keyfile=SSL_KEYFILE, ssl_certfile=SSL_CERTFILE)
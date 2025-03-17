# Ollama Auth Proxy

An authentication proxy server that adds API key support and OpenAI-compatible endpoints to Ollama.

## Features

- API key authentication for Ollama endpoints
- OpenAI API compatibility layer
- Support for both HTTP and HTTPS (with self-signed certificates)
- Easy integration with existing OpenAI client code

## Prerequisites

- Python 3.11 or higher
- Ollama running on the default port (11434)
- The proxy server must run on the same machine as Ollama (unless modified)

## Installation

1. Clone the repository:
```bash
git clone https://github.com/andrewcampi/ollama-auth-proxy
cd ollama-auth-proxy
```

2. Create and activate a virtual environment:
```bash
python3 -m venv venv
source venv/bin/activate  # On Unix/macOS
# Or on Windows:
# .\venv\Scripts\activate
```

3. Install dependencies:
```bash
python3 -m pip install -r requirements.txt
```

4. Create a `keys.json` file with your API keys:
```json
{
    "keys": [
        "sk-your-secure-key-1",
        "sk-your-secure-key-2"
    ]
}
```

## Running the Server

### Option 1: HTTPS (Recommended)

1. Generate self-signed certificates:
```bash
python3 generate_certs.py
```

2. Start the HTTPS server:
```bash
python3 auth_proxy_https.py
```

The server will run on port 8080 with HTTPS enabled.

### Option 2: HTTP (Not Recommended for Production)

Start the HTTP server:
```bash
python3 auth_proxy_http.py
```

## Client Integration

Check the `client_example_http.py` or `client_example_https.py` files for reference implementation. Here's a basic example using the OpenAI client:

```python
from openai import OpenAI
import httpx
import ssl
import certifi

# For HTTPS with self-signed certificates
ssl_context = ssl.create_default_context(cafile=certifi.where())
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_NONE
http_client = httpx.Client(verify=ssl_context)

client = OpenAI(
    api_key="sk-your-secure-key",  # Must match a key in keys.json
    base_url="https://localhost:8080",  # Use http:// for HTTP server
    http_client=http_client  # Only needed for HTTPS
)

response = client.chat.completions.create(
    model="mistral",  # Will be passed to Ollama
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Hello!"}
    ]
)
```

## Current Limitations

- Streaming responses are not yet supported
- Uses self-signed certificates for HTTPS
- Proxy code must run on the same machine as Ollama (unless modified)

## Security Considerations

- HTTPS with self-signed certificates is more secure than HTTP but may still be vulnerable to MiTM attacks. If using in production, modify the code and use a CA-signed cert.
- Consider implementing API key rotation for production use
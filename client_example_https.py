from openai import OpenAI
import httpx
import certifi
import ssl

# Create a custom SSL context that accepts self-signed certificates
ssl_context = ssl.create_default_context(cafile=certifi.where())
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_NONE

# Create a custom HTTP client with the SSL context
http_client = httpx.Client(verify=ssl_context)

# Configure the OpenAI client to point to your Ollama proxy
client = OpenAI(
    api_key="sk-my-random-key-here",  # Must match a key in keys.json
    base_url="https://localhost:8080",  # Point to your auth proxy
    http_client=http_client
)

# Make a request just like you would with the OpenAI API
response = client.chat.completions.create(
    model="mistral",  # This will be passed to Ollama
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Hello, who are you?"}
    ],
    temperature=0.7,
    max_tokens=500
)

# Print the response
print(response.choices[0].message.content)
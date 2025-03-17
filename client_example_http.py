from openai import OpenAI

# Configure the OpenAI client to point to your Ollama proxy
client = OpenAI(
    api_key="sk-my-random-key-here",  # Must match a key in keys.json
    base_url="http://localhost:8080"  # Point to your auth proxy
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
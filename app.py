import os
import logging
from flask import Flask, request, Response
import requests
from requests.exceptions import HTTPError
import codecs
from urllib.parse import unquote # Used for decoding URL encoded prompts
import json # Used for decoding URL encoded prompts

# Initialize the Flask web application and configure logging
app = Flask(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')

API_KEY = os.environ.get('API_KEY')

# Define handlers for different AI models
def process_gpt_3(response):
    # Older models
    return response['choices'][0]['text']

def process_gpt_3_5_turbo(response):
    # Newer chat based models
    return response['choices'][0]['message']['content']

def process_response(sourceResponse, ai_model):
    version_handlers = {
        'gpt-3.5-turbo': process_gpt_3_5_turbo,
        'gpt-3.5-turbo-0301': process_gpt_3_5_turbo,
        'default': process_gpt_3,  # Use the default handler for all other models
    }

    # Get the appropriate handler based on the user specified AI model
    handler = version_handlers.get(ai_model, version_handlers['default'])

    # Call the handler and return its result
    return handler(sourceResponse)

# Define a route to handle POST requests to the openai-proxy endpoint
@app.route('/openai-proxy', methods=['POST'])
def openai_proxy():
    data = request.get_data(as_text=True)
    logging.info(data)
    # Try extracting the JSON data from the incoming request
    try:
        data = request.get_json()
    except Exception as error:
        app.logger.error("🛑 Error parsing prompt JSON: %s", str(error))
        return Response(f"Error parsing prompt JSON: {error}", status=400, mimetype='text/plain') # Return the error to LegacyAI

    # Get custom request headers from LegacyAI
    ai_model = request.headers.get("AI-Model", "gpt-3.5-turbo")  # Use the default model if the header is not set
    initial_prompt = request.headers.get("Initial-Prompt", "You are a helpful assistant.")  # Use the default prompt if the header is not set
    url_encoded = request.headers.get("URL-Encoded", "Unknown")
    tokens = request.headers.get("Tokens", "Disabled")
    temp = request.headers.get("Temperature", "0.7")

    # Convert header strings to number values
    max_tokens = int(tokens)
    temperature = float(temp)

    # Check which type of encoding has been received from LegacyAI
    prompt = ''
    if url_encoded == 'true':
        # Decode 68k lossy URL-encoding
        raw_prompt = data['prompt']
        decoded_prompt = unquote(raw_prompt)
        clean_prompt = decoded_prompt.replace('\r', '\n') # Replace carriage returns with newlines
        prompt = clean_prompt
    elif url_encoded == 'false':
        # Handle UTF8 Encoding
        mac_roman_string = data['prompt']
        mac_roman_bytes = bytes(mac_roman_string, 'mac_roman')
        utf8_string = codecs.decode(mac_roman_bytes, 'utf_8')
        prompt = utf8_string
    else:
        # Use raw text if the encoding can't be determined
        prompt = data['prompt']

    ##### Logging ####
    # Log the request header information for debugging
    logging.info(f"\n🤖 AI Model: {ai_model}\n🌡 Temperature: {temp}\n⭐️ Max Tokens: {tokens}")

    # Prepare the headers for the request to the OpenAI API
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {API_KEY}'
    }

    try:
        # Send the request to the OpenAI API with the extracted JSON data and headers
        if ai_model in ['gpt-3.5-turbo', 'gpt-3.5-turbo-0301']:
            OPENAI_API_URL = f"https://api.openai.com/v1/chat/completions"
            data = {
                'model': ai_model,
                'temperature': temperature,
                'messages': [
                    {"role": "system", "content": initial_prompt},
                    {"role": "user", "content": prompt}
                ],
            }
        else:
            OPENAI_API_URL = f"https://api.openai.com/v1/engines/{ai_model}/completions"
            # The older models don't work well with initial prompts, so it should be removed.
            data = {
                'prompt': prompt,
                'temperature': temperature,
                'max_tokens': max_tokens
            }
        response = requests.post(OPENAI_API_URL, json=data, headers=headers)
        response.raise_for_status()  # Raises an HTTPError for 4xx and 5xx responses

    # Handle the response
    except HTTPError as http_err:
        response_dict = response.json()
        if response.status_code == 503:
            # Extract the error message and return it to the app
            error_message = response_dict.get('error', {}).get('message', '') 
            logging.error(f"OpenAI API request failed with status {response.status_code}: {response.text}")
            return Response(f"{error_message}", status=503, mimetype='text/plain')
        else:
            # Extract the error message and return it to the app
            error_message = response_dict.get('error', {}).get('message', '')
            logging.info(f"OpenAI API error: {error_message}")
            return Response(f"{error_message}", status=400, mimetype='text/plain') # Return the error to LegacyAI

    # Extract the JSON data from the response
    sourceResponse = response.json()

    # Check if the response has the expected structure
    if 'choices' not in sourceResponse:
        error_message = sourceResponse.get('error', {}).get('message', '') 
        logging.error(f"Unexpected OpenAI API response structure: {sourceResponse}")
        return Response(f"{error_message}", status=500, mimetype='text/plain')

    # Use the appropriate handler to process the response text
    try:
        text = process_response(sourceResponse, ai_model)
    except Exception as err:
        logging.error(f"An error occurred while processing the response: {err}")
        return Response("AI service returned an unexpected response.", status=500, mimetype='text/plain')

    # Remove unwanted newline and carriage return characters from the text
    text = text.lstrip("\n\r")

    # Replace newline characters with <br> for the remaining newlines
    # LegacyAI detects '<br>' elements to determine line breaks
    text_with_br = text.replace("\n", "<br>")

    # Log the cleaned response text
    # logging.info(f"\n🐸 Response: \n\n{text_with_br}\n")

    gpt_response = ''
    if url_encoded == 'true':
        # Convert the UTF8 text to Mac Roman. LegacyAI only has western language support.
        # Characters from unsupported languages are replaced with '?'
        gpt_response = text_with_br.encode('macroman', 'replace')
    else:
        gpt_response = text_with_br

    # Return the cleaned text as a plain-text HTTP response
    return Response(gpt_response, content_type='text/plain; charset=utf-8')

# Error handling
@app.errorhandler(Exception)
def handle_unexpected_error(error):
    app.logger.error(f"Unexpected error occurred: {error}")
    return Response(f"{error}", status=500, mimetype='text/plain')

@app.errorhandler(400)
def handle_bad_request(error):
    app.logger.error(f"Bad Request: {error}")
    return Response(f"Bad Request: {error}", status=400, mimetype='text/plain')
@app.errorhandler(500)
def handle_server_error(error):
    app.logger.error(f"Bad Request: {error}")
    return Response(f"Server Error: {error}", status=500, mimetype='text/plain')


# Define a route for the root path to confirm the server is running
@app.route('/')
def home():
    return "OpenAI API proxy server is running."

# Run the Flask web application, listening on all interfaces and using the PORT environment variable or 8080 as default
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))


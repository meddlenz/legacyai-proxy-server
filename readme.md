# Example Proxy Server for [LegacyAI](https://manticore.nz/legacyai)
This is an example implementation of a basic proxy server used to communicate with OpenAI's API. Once your server is set up and running you can add it's URL/endpoint to LegacyAI's Proxy Server field.

## Prerequisites You will need:
- An OpenAI API key
- A Heroku account attached any of their dyno plans

## Setup steps 
Follow the [setup guide on Mac-Classic.com](https://mac-classic.com/articles/setting-up-a-legacyai-proxy-server/) to create a Heroku instance with the contents of this repository. When your server is running you can add it to LegacyAI which will bypass the default server, and use yours instead.

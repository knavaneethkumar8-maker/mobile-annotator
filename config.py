# config.py
# Set this to False for local development, True for server deployment
USE_BASE_PATH = False  # Change this manually: False for local, True for server

# Base path configuration
BASE_PATH = "/mobile-annotator" if USE_BASE_PATH else ""

# Server configuration
DEBUG = not USE_BASE_PATH  # Auto debug mode for local development
HOST = '0.0.0.0'
PORT = 8889
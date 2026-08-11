"""Configuration for Paper Agent."""
import os
from dotenv import load_dotenv
load_dotenv()

INPUT_DIR = os.path.join(os.path.dirname(__file__), "input", "papers")
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")


class Config:
    def __init__(self):
        self.input_dir = INPUT_DIR
        self.output_dir = OUTPUT_DIR
        self.model = os.getenv("MODEL", "Longcat-2.0")
        self.api_key = os.getenv("API_KEY", "testapi")
        self.base_url = os.getenv("BASE_URL", "https://api.longcat.chat/openai/v1")
        self.temperature = 0.2
        self.max_tokens = 8192
        self.evaluation_topic = os.getenv("EVALUATION_TOPIC", "AI赋能")

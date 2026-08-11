"""LLM API client wrapper."""
from openai import OpenAI
from config import Config
import os
from dotenv import load_dotenv

load_dotenv()

class LLMClient:
    def __init__(self,Config):
        self.api_key=Config.api_key
        self.model=Config.model
        self.base_url=Config.base_url
        if not self.api_key:
            raise ValueError("缺少 API Key，请设置 LONGCAT_API_KEY 环境变量，或在初始化时传入 api_key")
        self.client= OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
        )
    


    def chat(self,system_prompt,user_prompt):

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role":"system",
                "content":system_prompt},
                {"role":"user",
                "content":user_prompt
                },
            ]
        )

        return response.choices[0].message.content

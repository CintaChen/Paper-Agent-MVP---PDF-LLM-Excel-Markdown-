import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(
    api_key=os.getenv("API_KEY"),  # 如果你用的是别的变量名，改成对应的
    base_url=os.getenv("BASE_URL"),
)

print("BASE_URL:", repr(os.getenv("BASE_URL")))
print("MODEL:", repr(os.getenv("MODEL")))

response = client.chat.completions.create(
    model=os.getenv("MODEL"),
    messages=[
        {"role": "user", "content": "你好"}
    ]
)

print(response.choices[0].message.content)
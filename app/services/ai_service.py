import os
from dotenv import load_dotenv
import anthropic

load_dotenv()

api_key = os.getenv("ANTHROPIC_API_KEY")

client = anthropic.Anthropic(api_key=api_key)

def analyze_log(log_text: str):
    if not api_key:
        return "Hata: ANTHROPIC_API_KEY bulunamadi."

    try:
        msg = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=600,
            system="You are an ASIC EDA assistant.",
            messages=[
                {
                    "role": "user",
                    "content": f"""
Analyze this EDA tool log.

Return:
- summary
- success or fail
- possible reason
- next step

Log:
{log_text}
"""
                }
            ]
        )

        parts = []
        for block in msg.content:
            if getattr(block, "type", None) == "text":
                parts.append(block.text)

        return "\n".join(parts).strip()

    except Exception as e:
        return f"Anthropic API hatasi: {str(e)}"

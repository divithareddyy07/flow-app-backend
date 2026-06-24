import os
import re
import json
from flask import Flask, request, jsonify
from flask_cors import CORS
from groq import Groq
from dotenv import load_dotenv
from duckduckgo_search import DDGS

load_dotenv()

app = Flask(__name__)
CORS(app)

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

EDODWAJA_FACTS = """
FACTS ABOUT EDODWAJA (use these when asked):
- Edodwaja is a Hyderabad-based startup founded by Madhulash Babu Krovvidi
- Madhulash Babu is a BTech Electronics graduate and Forbes 30 Under 30 Asia 2026 honoree
- Edodwaja built India first AI-powered mobile laboratory called the FLOW Bus (Futuristic Lab on Wheels)
- The FLOW Bus has reached over 60,000 students in rural areas across Telangana and Andhra Pradesh
- The FLOW Bus is equipped with robotics, AR/VR, drone technology, 3D printing, holograms, and a mobile planetarium
- The bus runs on solar power and accommodates 30-35 people at once
- Edodwaja mission is making tech education accessible to students in government and rural schools
- FLOW APP (FLOW LENS + FLOW TUTOR) are AI tools built by Edodwaja interns for the FLOW Bus experience
"""

def search_web(query):
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=3))
            if results:
                combined = ""
                for r in results:
                    combined += f"Title: {r.get('title','')}\nInfo: {r.get('body','')}\n\n"
                return combined.strip()
    except:
        pass
    return ""

def needs_search(question):
    keywords = [
        "who is", "what is", "founder", "ceo", "owner", "when was", "where is",
        "how many", "latest", "recent", "news", "current", "price", "born",
        "history", "invented", "discovered", "located", "population", "capital",
        "president", "minister", "company", "startup", "profile", "about"
    ]
    q = question.lower()
    return any(k in q for k in keywords)

def extract_json(text):
    text = re.sub(r"```json|```", "", text).strip()
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        return match.group(0)
    return text

def clean_and_parse(raw):
    try:
        return json.loads(raw)
    except:
        pass
    try:
        return json.loads(extract_json(raw))
    except:
        pass
    try:
        fixed = re.sub(r',\s*}', '}', raw)
        fixed = re.sub(r',\s*]', ']', fixed)
        return json.loads(extract_json(fixed))
    except:
        pass
    return None

@app.route("/analyse", methods=["POST"])
def analyse():
    try:
        data = request.get_json()
        image_data = data.get("image", "")
        if "," in image_data:
            image_data = image_data.split(",")[1]

        prompt = """You are a powerful visual AI. Analyse EVERYTHING in this image completely.
Return ONLY a valid JSON object. No text before or after. No markdown. No code blocks.

For MATH, STATISTICS, AUTOMATA, DFA, NFA, PHYSICS, CHEMISTRY, any academic problems:
{"mode":"math","title":"what type","solution":"solve every problem completely with full working and actual answers","steps":["Q1: complete solution","Q2: complete solution"],"concept":"subject and topic","tip":"study tip"}

For CODE or ERRORS:
{"mode":"code","title":"language and problem","what_is_wrong":"explain bug clearly","fixed_code":"complete corrected code","explanation":"why fix works","tip":"best practice"}

For CIRCUITS, ELECTRONICS, WIRING:
{"mode":"circuit","title":"circuit name","what_it_does":"what it does","components":["part1","part2"],"wiring":"exact pin by pin connections with pin numbers","how_it_works":"how it works step by step","common_mistakes":"mistakes to avoid"}

For ANYTHING ELSE:
{"mode":"object","object_name":"exact name","what_it_is":"2-3 sentences description","how_it_works":"how it works or functions","where_it_is_used":["use1","use2","use3","use4","use5"],"wiring_guide":null,"field":"field","difficulty_to_learn":"Easy / Moderate / Advanced","fun_fact":"fascinating fact","related_careers":["career1","career2","career3"]}

IMPORTANT: Return ONLY the JSON. Nothing else."""

        response = client.chat.completions.create(
            model="meta-llama/llama-4-scout-17b-16e-instruct",
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_data}"}},
                    {"type": "text", "text": prompt}
                ]
            }],
            max_tokens=2000,
            temperature=0.1
        )

        raw = response.choices[0].message.content.strip()
        result = clean_and_parse(raw)

        if result:
            return jsonify(result)
        else:
            plain = client.chat.completions.create(
                model="meta-llama/llama-4-scout-17b-16e-instruct",
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_data}"}},
                        {"type": "text", "text": "Analyse everything in this image. Solve all problems with complete working. Use plain text only, no markdown, no asterisks. Number each question clearly."}
                    ]
                }],
                max_tokens=2000,
                temperature=0.1
            )
            plain_text = plain.choices[0].message.content.strip()
            plain_text = re.sub(r'\*\*|\*|#{1,6} |`{1,3}', '', plain_text)
            return jsonify({"mode": "raw", "content": plain_text})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/lens-chat", methods=["POST"])
def lens_chat():
    try:
        data = request.get_json()
        messages = data.get("messages", [])
        image_data = data.get("image", None)
        language = data.get("language", "English")

        system_prompt = f"""You are FLOW LENS AI by EDODWAJA. You can see images and answer any question.
Reply ONLY in {language}.
- If Telugu: use Telugu script
- If Hindi: use Hindi script
- If English: use simple English
Be clear and helpful. For math show full working. For code show corrected version.
For electronics give exact pin numbers. Use plain text only.


FACTS ABOUT EDODWAJA:
- Founded by Madhulash Babu Krovvidi
- Built FLOW Bus — India first AI-powered mobile lab
- Reached 60000+ students in Telangana and Andhra Pradesh
- Madhulash Babu is Forbes 30 Under 30 Asia 2026 honoree
- FLOW Bus has robotics, AR/VR, drones, 3D printing, holograms, planetarium
- Runs on solar power, accommodates 30-35 students at once
"""

        groq_messages = [{"role": "system", "content": system_prompt}]
        for i, msg in enumerate(messages):
            if msg["role"] == "user" and i == len(messages) - 1 and image_data:
                image_b64 = image_data
                if "," in image_b64:
                    image_b64 = image_b64.split(",")[1]
                groq_messages.append({
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
                        {"type": "text", "text": msg["content"]}
                    ]
                })
            else:
                groq_messages.append({"role": msg["role"], "content": msg["content"]})

        response = client.chat.completions.create(
            model="meta-llama/llama-4-scout-17b-16e-instruct",
            messages=groq_messages,
            max_tokens=1000
        )
        reply = response.choices[0].message.content.strip()
        reply = re.sub(r'\*\*|\*|#{1,6} ', '', reply)
        return jsonify({"reply": reply})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/tutor-chat", methods=["POST"])
def tutor_chat():
    try:
        data = request.get_json()
        messages = data.get("messages", [])
        language = data.get("language", "English")

        last_question = ""
        for msg in reversed(messages):
            if msg["role"] == "user":
                last_question = msg["content"]
                break

        web_context = ""
        if last_question and needs_search(last_question):
            web_context = search_web(last_question)

        system_prompt = f"""You are a helpful AI assistant. Answer any question accurately and clearly.
Always reply ONLY in {language}.
- If Telugu: reply in Telugu script
- If Hindi: reply in Hindi script
- If English: reply in simple English
Never make up facts. Short answers for simple questions, detailed for complex ones.


FACTS ABOUT EDODWAJA:
- Founded by Madhulash Babu Krovvidi
- Built FLOW Bus — India first AI-powered mobile lab
- Reached 60000+ students in Telangana and Andhra Pradesh
- Madhulash Babu is Forbes 30 Under 30 Asia 2026 honoree
- FLOW Bus has robotics, AR/VR, drones, 3D printing, holograms, planetarium
- Runs on solar power, accommodates 30-35 students at once
"""

        if web_context:
            system_prompt += f"\n\nWeb search results (use to answer accurately):\n{web_context}"

        groq_messages = [{"role": "system", "content": system_prompt}]
        for msg in messages:
            groq_messages.append({"role": msg["role"], "content": msg["content"]})

        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=groq_messages,
            max_tokens=800
        )
        reply = response.choices[0].message.content.strip()
        reply = re.sub(r'\*\*|\*|#{1,6} ', '', reply)
        return jsonify({"reply": reply, "language": language})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/", methods=["GET"])
def health():
    return jsonify({"status": "FLOW APP running"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=True)

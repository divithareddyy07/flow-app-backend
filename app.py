import os
import re
import json
import requests
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from groq import Groq
from dotenv import load_dotenv
from duckduckgo_search import DDGS

load_dotenv()

app = Flask(__name__)
CORS(app)

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

JSONBIN_BIN_ID = os.getenv("JSONBIN_BIN_ID", "6a421c9dda38895dfe0e83ae")
JSONBIN_SECRET = os.getenv("JSONBIN_SECRET", "$2a$10$/YRpHMqXno3QxCe8t2iJquzHVY7i63FdhzY0OA3mtemlqwBc6iG.O")
JSONBIN_URL = f"https://api.jsonbin.io/v3/b/{JSONBIN_BIN_ID}"
JSONBIN_HEADERS = {
    "X-Master-Key": JSONBIN_SECRET,
    "Content-Type": "application/json"
}

def load_kb():
    try:
        res = requests.get(JSONBIN_URL, headers=JSONBIN_HEADERS)
        return res.json().get("record", {"items": []})
    except:
        return {"items": []}

def save_kb(kb):
    try:
        requests.put(JSONBIN_URL, headers=JSONBIN_HEADERS, json=kb)
    except:
        pass

EDODWAJA_FACTS = """
FACTS ABOUT EDODWAJA:
- Founded by Madhulash Babu Krovvidi
- Built FLOW Bus - India first AI-powered mobile lab
- Reached 60000+ students in Telangana and Andhra Pradesh
- Madhulash Babu is Forbes 30 Under 30 Asia 2026 honoree
- FLOW Bus has robotics, AR/VR, drones, 3D printing, holograms, planetarium
- Runs on solar power, accommodates 30-35 students at once
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
    keywords = ["who is","what is","founder","ceo","when was","where is","how many","latest","recent","news","current","born","history","invented","located","population","capital","president","minister","company","startup","about"]
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

def get_kb_context():
    kb = load_kb()
    if not kb.get("items"):
        return ""
    context = "\n\nFLOW BUS KNOWLEDGE BASE - These are items in the FLOW Bus. When you see any of these in the image, use the provided description:\n"
    for item in kb["items"]:
        context += f"\nITEM: {item['name']}\nDESCRIPTION: {item['description']}\n"
    return context

def find_matching_kb_item(image_b64):
    kb = load_kb()
    items = kb.get("items", [])
    if not items:
        return None
    
    items_text = ""
    for item in items:
        items_text += f"- ID:{item['id']} NAME:{item['name']}\n"
    
    try:
        response = client.chat.completions.create(
            model="meta-llama/llama-4-scout-17b-16e-instruct",
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
                    {"type": "text", "text": f"""Look at this image carefully. Does it match any of these items?

{items_text}

If the image matches one of these items, reply with ONLY the ID number like: MATCH:1
If no match found, reply with: MATCH:0"""}
                ]
            }],
            max_tokens=50,
            temperature=0.1
        )
        result = response.choices[0].message.content.strip()
        if "MATCH:" in result:
            match_id = int(result.split("MATCH:")[1].strip())
            if match_id > 0:
                for item in items:
                    if item["id"] == match_id:
                        return item
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

        kb_context = get_kb_context()

        # Check if image matches any knowledge base item
        matched_item = find_matching_kb_item(image_data)
        if matched_item:
            return jsonify({
                "mode": "object",
                "object_name": matched_item["name"],
                "what_it_is": matched_item["description"],
                "how_it_works": matched_item["description"],
                "where_it_is_used": ["FLOW Bus", "Educational demonstrations", "Student learning", "Technology exhibitions", "Hands-on workshops"],
                "wiring_guide": None,
                "field": "Educational Technology",
                "difficulty_to_learn": "Moderate",
                "fun_fact": f"This is part of the FLOW Bus — India's first AI-powered mobile laboratory!",
                "related_careers": ["Robotics Engineer", "AI Developer", "Technology Educator"]
            })

        prompt = f"""You are a powerful visual AI for the EDODWAJA FLOW Bus.{kb_context}

Analyse EVERYTHING in this image. If you recognise a FLOW Bus component or robot from the knowledge base above, use that information to give a detailed response.

Return ONLY a valid JSON object. No text before or after. No markdown. No code blocks.

For MATH, STATISTICS, AUTOMATA, DFA, NFA, PHYSICS, CHEMISTRY, any academic problems:
{{"mode":"math","title":"what type","solution":"solve every problem completely with full working and actual answers","steps":["Q1: complete solution","Q2: complete solution"],"concept":"subject and topic","tip":"study tip"}}

For CODE or ERRORS:
{{"mode":"code","title":"language and problem","what_is_wrong":"explain bug clearly","fixed_code":"complete corrected code","explanation":"why fix works","tip":"best practice"}}

For CIRCUITS, ELECTRONICS, WIRING:
{{"mode":"circuit","title":"circuit name","what_it_does":"what it does","components":["part1","part2"],"wiring":"exact pin by pin connections with pin numbers","how_it_works":"how it works step by step","common_mistakes":"mistakes to avoid"}}

For FLOW BUS COMPONENTS, ROBOTS, or ANY OTHER OBJECT:
{{"mode":"object","object_name":"exact name","what_it_is":"detailed description - use knowledge base if available","how_it_works":"how it works or functions","where_it_is_used":["use1","use2","use3","use4","use5"],"wiring_guide":null,"field":"field","difficulty_to_learn":"Easy / Moderate / Advanced","fun_fact":"fascinating fact","related_careers":["career1","career2","career3"]}}

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
                        {"type": "text", "text": "Analyse everything in this image. Use plain text only, no markdown."}
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
        kb_context = get_kb_context()

        system_prompt = f"""You are FLOW LENS AI by EDODWAJA. You can see images and answer any question.
Reply ONLY in {language}.
{EDODWAJA_FACTS}
{kb_context}"""

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

        system_prompt = f"""You are a helpful AI assistant. Answer any question accurately.
Always reply ONLY in {language}.
{EDODWAJA_FACTS}"""

        if web_context:
            system_prompt += f"\n\nWeb search results:\n{web_context}"

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

@app.route("/admin/items", methods=["GET"])
def get_items():
    kb = load_kb()
    items_without_image = []
    for item in kb.get("items", []):
        items_without_image.append({
            "id": item["id"],
            "name": item["name"],
            "description": item["description"],
            "has_image": bool(item.get("image"))
        })
    return jsonify(items_without_image)

@app.route("/admin/add", methods=["POST"])
def add_item():
    try:
        data = request.get_json()
        kb = load_kb()
        items = kb.get("items", [])
        new_id = max([i["id"] for i in items], default=0) + 1
        new_item = {
            "id": new_id,
            "name": data.get("name", ""),
            "description": data.get("description", ""),
            "image": data.get("image", "")
        }
        items.append(new_item)
        kb["items"] = items
        save_kb(kb)
        return jsonify({"success": True, "id": new_id})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/admin/delete/<int:item_id>", methods=["DELETE"])
def delete_item(item_id):
    try:
        kb = load_kb()
        kb["items"] = [i for i in kb.get("items", []) if i["id"] != item_id]
        save_kb(kb)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "flowbus2024")

# Store credentials in memory (persists until Render restarts)
current_credentials = {"username": None, "password": None}

def get_credentials():
    return (
        current_credentials["username"] or os.getenv("ADMIN_USERNAME", "admin"),
        current_credentials["password"] or os.getenv("ADMIN_PASSWORD", "flowbus2024")
    )

@app.route("/admin/change-credentials", methods=["POST"])
def change_credentials():
    data = request.get_json()
    if data.get("token") != "flowbus_admin_token":
        return jsonify({"success": False}), 401
    current_credentials["username"] = data.get("username")
    current_credentials["password"] = data.get("password")
    return jsonify({"success": True})

@app.route("/admin/login", methods=["POST"])
def admin_login():
    data = request.get_json()
    uname, pwd = get_credentials()
    if data.get("username") == uname and data.get("password") == pwd:
        return jsonify({"success": True, "token": "flowbus_admin_token"})
    return jsonify({"success": False, "message": "Invalid credentials"}), 401

@app.route("/admin", methods=["GET"])
def admin_panel():
    return send_file("admin.html")

@app.route("/", methods=["GET"])
def health():
    return jsonify({"status": "FLOW APP running"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=True)

import os
import re
import json
import base64
import uuid
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from groq import Groq
from dotenv import load_dotenv
from duckduckgo_search import DDGS
from supabase import create_client, Client

load_dotenv()

app = Flask(__name__)
CORS(app)

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

SUPABASE_URL = os.getenv("SUPABASE_URL", "https://vrexvfqubmpfxkwsadxm.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InZyZXh2ZnF1Ym1wZnhrd3NhZHhtIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc4Mjc5MzQ5NiwiZXhwIjoyMDk4MzY5NDk2fQ.SfYXfkRb1KsHSFP5uwUTFMN5zXlwjWa-y860jHsi51w")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

current_credentials = {"username": None, "password": None}

def get_credentials():
    return (
        current_credentials["username"] or os.getenv("ADMIN_USERNAME", "admin"),
        current_credentials["password"] or os.getenv("ADMIN_PASSWORD", "flowbus2024")
    )

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

# ── KNOWLEDGE BASE (Supabase) ──

def get_all_kb_items():
    try:
        result = supabase.table("knowledge_base").select("*").execute()
        return result.data
    except Exception as e:
        print(f"Supabase fetch error: {e}")
        return []

def upload_image_to_storage(image_b64, filename):
    try:
        image_bytes = base64.b64decode(image_b64)
        supabase.storage.from_("flow-images").upload(
            filename, image_bytes, {"content-type": "image/jpeg"}
        )
        public_url = supabase.storage.from_("flow-images").get_public_url(filename)
        return public_url
    except Exception as e:
        print(f"Image upload error: {e}")
        return None

def find_matching_kb_item(image_b64):
    items = get_all_kb_items()
    if not items:
        return None

    # Build content with BOTH the student photo AND all reference photos
    content_blocks = [
        {"type": "text", "text": "This is the PHOTO TO IDENTIFY (taken by a student):"},
        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
        {"type": "text", "text": "\nNow here are the REFERENCE ITEMS in the knowledge base. Compare the photo above to each one:"}
    ]

    valid_items = []
    for item in items:
        if item.get("image_url"):
            content_blocks.append({"type": "text", "text": f"\nReference ID:{item['id']} NAME:{item['name']}"})
            content_blocks.append({"type": "image_url", "image_url": {"url": item["image_url"]}})
            valid_items.append(item)

    if not valid_items:
        return None

    content_blocks.append({
        "type": "text",
        "text": "\n\nWhich reference ID visually matches the photo to identify? They must be the same physical object (same colors, shape, build), not just similar category. Reply ONLY with: MATCH:ID or MATCH:0 if none match."
    })

    try:
        response = client.chat.completions.create(
            model="meta-llama/llama-4-scout-17b-16e-instruct",
            messages=[{"role": "user", "content": content_blocks}],
            max_tokens=20,
            temperature=0.0
        )
        result = response.choices[0].message.content.strip()
        if "MATCH:" in result:
            try:
                match_id = int(result.split("MATCH:")[1].strip().split()[0])
                if match_id > 0:
                    for item in valid_items:
                        if item["id"] == match_id:
                            return item
            except:
                pass
    except Exception as e:
        print(f"Matching error: {e}")
    return None

def generate_full_description(name, description):
    """Use AI to expand a basic description into the full FLOW LENS object format"""
    try:
        prompt = f"""Based on this item information:
Name: {name}
Description: {description}

Generate supporting educational fields ONLY - do NOT rewrite the description, use it as context. Return ONLY valid JSON:
{{
  "how_it_works": "explain how this item works, based on the description, 3-4 sentences",
  "where_it_is_used": ["use case 1", "use case 2", "use case 3", "use case 4", "use case 5"],
  "field": "relevant field or domain",
  "difficulty_to_learn": "Easy or Moderate or Advanced",
  "fun_fact": "an interesting fact related to this item",
  "related_careers": ["career1", "career2", "career3"]
}}

Return ONLY the JSON."""

        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=800,
            temperature=0.3
        )
        raw = response.choices[0].message.content.strip()
        result = clean_and_parse(raw)
        return result
    except Exception as e:
        print(f"Description generation error: {e}")
        return None

def get_kb_context():
    items = get_all_kb_items()
    if not items:
        return ""
    context = "\n\nFLOW BUS KNOWLEDGE BASE:\n"
    for item in items:
        context += f"- {item['name']}: {item['description']}\n"
    return context

def analyse_with_ai(image_b64, kb_context=""):
    prompt = f"""You are a powerful visual AI for the EDODWAJA FLOW Bus.{kb_context}

Analyse EVERYTHING in this image completely.
Return ONLY a valid JSON object. No text before or after. No markdown. No code blocks.

For MATH, STATISTICS, AUTOMATA, DFA, NFA, PHYSICS, CHEMISTRY, any academic problems:
{{"mode":"math","title":"what type","solution":"solve every problem completely with full working and actual answers","steps":["Q1: complete solution","Q2: complete solution"],"concept":"subject and topic","tip":"study tip"}}

For CODE or ERRORS:
{{"mode":"code","title":"language and problem","what_is_wrong":"explain bug clearly","fixed_code":"complete corrected code","explanation":"why fix works","tip":"best practice"}}

For CIRCUITS, ELECTRONICS, WIRING:
{{"mode":"circuit","title":"circuit name","what_it_does":"what it does","components":["part1","part2"],"wiring":"exact pin by pin connections with pin numbers","how_it_works":"how it works step by step","common_mistakes":"mistakes to avoid"}}

For ANYTHING ELSE - objects, people, places, animals, food, products:
{{"mode":"object","object_name":"exact name","what_it_is":"detailed description","how_it_works":"how it works or functions","where_it_is_used":["use1","use2","use3","use4","use5"],"wiring_guide":null,"field":"field","difficulty_to_learn":"Easy / Moderate / Advanced","fun_fact":"fascinating fact","related_careers":["career1","career2","career3"]}}

IMPORTANT: Return ONLY the JSON. Nothing else."""

    response = client.chat.completions.create(
        model="meta-llama/llama-4-scout-17b-16e-instruct",
        messages=[{
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
                {"type": "text", "text": prompt}
            ]
        }],
        max_tokens=2000,
        temperature=0.1
    )
    return response.choices[0].message.content.strip()

@app.route("/analyse", methods=["POST"])
def analyse():
    try:
        data = request.get_json()
        image_data = data.get("image", "")
        if "," in image_data:
            image_data = image_data.split(",")[1]

        # Step 1 — check knowledge base for image match
        matched_item = find_matching_kb_item(image_data)
        if matched_item:
            # Generate ONLY the supporting fields using AI - keep description exactly as typed
            full_desc = generate_full_description(matched_item["name"], matched_item["description"])
            if full_desc:
                return jsonify({
                    "mode": "object",
                    "object_name": matched_item["name"],
                    "what_it_is": matched_item["description"],
                    "how_it_works": full_desc.get("how_it_works", ""),
                    "where_it_is_used": full_desc.get("where_it_is_used", ["FLOW Bus"]),
                    "wiring_guide": None,
                    "field": full_desc.get("field", "Educational Technology"),
                    "difficulty_to_learn": full_desc.get("difficulty_to_learn", "Moderate"),
                    "fun_fact": full_desc.get("fun_fact", "Part of the FLOW Bus by EDODWAJA!"),
                    "related_careers": full_desc.get("related_careers", ["Robotics Engineer", "AI Developer"])
                })
            else:
                return jsonify({
                    "mode": "object",
                    "object_name": matched_item["name"],
                    "what_it_is": matched_item["description"],
                    "how_it_works": matched_item["description"],
                    "where_it_is_used": ["FLOW Bus", "Educational demonstrations", "Student learning"],
                    "wiring_guide": None,
                    "field": "Educational Technology",
                    "difficulty_to_learn": "Moderate",
                    "fun_fact": "Part of the FLOW Bus by EDODWAJA!",
                    "related_careers": ["Robotics Engineer", "AI Developer"]
                })

        # Step 2 — no match, analyse normally
        kb_context = get_kb_context()
        raw = analyse_with_ai(image_data, kb_context)
        result = clean_and_parse(raw)

        if result:
            return jsonify(result)
        else:
            plain_response = client.chat.completions.create(
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
            plain_text = plain_response.choices[0].message.content.strip()
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

        kb_context = get_kb_context()

        system_prompt = f"""You are an experienced, friendly teacher talking directly to a curious student. Speak naturally like a real teacher in a classroom — warm, clear, and enthusiastic.

Always reply ONLY in {language}.
- If Telugu: reply in Telugu script, speak like a Telugu teacher talking to a student
- If Hindi: reply in Hindi script, speak like a Hindi teacher talking to a student  
- If English: reply in simple conversational English like a teacher explaining to a student

TONE RULES:
- Talk TO the student directly — use "you", "let me explain", "great question!", "think of it this way"
- Never say "The FLOW Bus teaches" or "EDODWAJA presents" — just teach naturally
- Use simple analogies and real-life examples students can relate to
- Be encouraging — "That is a really good question!", "You are going to love this!"
- Keep answers conversational, not like reading from a textbook
- End with something that sparks curiosity — a follow-up fact or "Want to know more about...?"

{EDODWAJA_FACTS}

{kb_context}

KNOWLEDGE RULES:
- When answering about items in the FLOW BUS KNOWLEDGE BASE above, use that as your primary source but explain it in your own teaching style
- Answer questions even if asked differently or paraphrased — understand the intent
- Never make up facts"""

        if web_context:
            system_prompt += f"\n\nAdditional web context:\n{web_context}"

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

# ── ADMIN ROUTES ──

@app.route("/admin/login", methods=["POST"])
def admin_login():
    data = request.get_json()
    uname, pwd = get_credentials()
    if data.get("username") == uname and data.get("password") == pwd:
        return jsonify({"success": True, "token": "flowbus_admin_token"})
    return jsonify({"success": False, "message": "Invalid credentials"}), 401

@app.route("/admin/change-credentials", methods=["POST"])
def change_credentials():
    data = request.get_json()
    if data.get("token") != "flowbus_admin_token":
        return jsonify({"success": False}), 401
    current_credentials["username"] = data.get("username")
    current_credentials["password"] = data.get("password")
    return jsonify({"success": True})

@app.route("/admin/items", methods=["GET"])
def get_items():
    items = get_all_kb_items()
    return jsonify(items)

@app.route("/admin/add", methods=["POST"])
def add_item():
    try:
        data = request.get_json()
        name = data.get("name", "")
        description = data.get("description", "")
        image_b64 = data.get("image", "")

        image_url = None
        if image_b64:
            if "," in image_b64:
                image_b64_clean = image_b64.split(",")[1]
            else:
                image_b64_clean = image_b64
            filename = f"{uuid.uuid4()}.jpg"
            image_url = upload_image_to_storage(image_b64_clean, filename)

        result = supabase.table("knowledge_base").insert({
            "name": name,
            "description": description,
            "image_url": image_url
        }).execute()

        return jsonify({"success": True, "id": result.data[0]["id"]})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/admin/delete/<int:item_id>", methods=["DELETE"])
def delete_item(item_id):
    try:
        supabase.table("knowledge_base").delete().eq("id", item_id).execute()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/admin", methods=["GET"])
def admin_panel():
    return send_file("admin.html")

@app.route("/", methods=["GET"])
def health():
    return jsonify({"status": "FLOW APP running"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=True)

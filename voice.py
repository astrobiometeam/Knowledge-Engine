from flask import Flask, request, send_file, jsonify
from flask_cors import CORS
from gtts import gTTS
import uuid

app = Flask(__name__)
CORS(app)  

def generate_tts(text, lang="en"):
    
    filename = f"tts_{uuid.uuid4().hex}.mp3"
    tts = gTTS(text=text, lang=lang)
    tts.save(filename)
    return filename

@app.route("/api/tts", methods=["GET", "POST"])
def tts():
    if request.method == "POST":
        data = request.get_json()
        text = data.get("text", "")
        lang = data.get("lang", "en")
    else:  
        text = request.args.get("text", "")
        lang = request.args.get("lang", "en")

    if not text.strip():
        return jsonify({"error": "Text is required"}), 400

    
    filename = generate_tts(text, lang)

    
    return send_file(filename, mimetype="audio/mpeg", as_attachment=False)

if __name__ == "__main__":
    app.run(debug=True, port=5001)

import os
import json
from flask import Flask, jsonify, render_template, request, Response, send_file
import io

from services.parser import parse_whatsapp_text, anonymize_messages
from services.stylometrics import compute_stats
from services.llm import test_connection, call_llm, DEFAULT_MODELS
from services.assembler import (
    sample_dialogue,
    extract_profile,
    pick_examples,
    build_system_prompt,
    build_character_card,
)

# In-memory storage for active sessions / results
CACHE = {}


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY", "dev-persona-cloner-secret"),
        MAX_CONTENT_LENGTH=32 * 1024 * 1024,  # 32MB max upload
    )

    if test_config is not None:
        app.config.from_mapping(test_config)

    @app.route("/")
    def index():
        return render_template("index.html", default_models=DEFAULT_MODELS)

    @app.route("/api/health")
    def health():
        return jsonify({"status": "ok", "app": "persona-cloner"})

    @app.route("/api/default-models")
    def get_default_models():
        return jsonify(DEFAULT_MODELS)

    @app.route("/api/test-connection", methods=["POST"])
    def api_test_connection():
        data = request.get_json() or {}
        provider = data.get("provider", "openrouter")
        api_key = data.get("api_key") or os.environ.get("OPENROUTER_API_KEY", "")
        model = data.get("model", "deepseek/deepseek-v4.1-flash")
        base_url = data.get("base_url")

        success, message = test_connection(
            api_key=api_key,
            model=model,
            provider=provider,
            base_url=base_url,
        )
        return jsonify({"success": success, "message": message}), (200 if success else 400)

    @app.route("/api/parse-chat", methods=["POST"])
    def api_parse_chat():
        content = ""
        if "file" in request.files:
            uploaded_file = request.files["file"]
            content = uploaded_file.read().decode("utf-8", errors="ignore")
        elif request.is_json:
            content = request.get_json().get("chat_text", "")

        if not content.strip():
            return jsonify({"success": False, "error": "No chat content provided."}), 400

        try:
            df, media_counts, participants = parse_whatsapp_text(content)
            CACHE["last_raw_text"] = content

            sample = []
            for _, row in df.head(5).iterrows():
                sample.append({
                    "datetime": row["datetime"].strftime("%Y-%m-%d %H:%M:%S") if hasattr(row["datetime"], "strftime") else str(row["datetime"]),
                    "sender": row["sender"],
                    "text": row["text"][:120],
                })

            date_range = [
                df["datetime"].min().strftime("%Y-%m-%d") if not df.empty else "",
                df["datetime"].max().strftime("%Y-%m-%d") if not df.empty else "",
            ]

            return jsonify({
                "success": True,
                "total_messages": len(df),
                "participants": participants,
                "date_range": date_range,
                "sample": sample,
            })
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 400

    @app.route("/api/generate-persona", methods=["POST"])
    def api_generate_persona():
        data = request.get_json() or {}
        chat_text = data.get("chat_text") or CACHE.get("last_raw_text", "")
        target_name = data.get("target_name")
        char_name = data.get("char_name") or target_name or "Fossetta"
        user_aliases = data.get("user_aliases") or []
        char_aliases = data.get("char_aliases") or []
        third_party_names = data.get("third_party_names") or []

        llm_config = {
            "provider": data.get("provider", "openrouter"),
            "api_key": data.get("api_key") or os.environ.get("OPENROUTER_API_KEY", ""),
            "model": data.get("model", "deepseek/deepseek-v4.1-flash"),
            "base_url": data.get("base_url"),
        }

        if not chat_text.strip():
            return jsonify({"success": False, "error": "Chat text is missing. Please upload your WhatsApp export file."}), 400
        if not target_name:
            return jsonify({"success": False, "error": "Target sender name must be selected."}), 400

        def event_stream():
            try:
                # Step 1: Parse & Anonymize
                yield f"data: {json.dumps({'step': 1, 'name': 'parsing', 'status': 'running', 'message': 'Parsing WhatsApp messages and scrubbing names...'})}\n\n"
                df_raw, media_counts, _ = parse_whatsapp_text(chat_text)
                df_anon, resolved_target = anonymize_messages(
                    df_raw,
                    target_name=target_name,
                    char_name=char_name,
                    user_aliases=user_aliases,
                    char_aliases=char_aliases,
                    third_party_names=third_party_names,
                )
                yield f"data: {json.dumps({'step': 1, 'name': 'parsing', 'status': 'completed', 'message': f'Parsed {len(df_anon)} messages. Target identified as {resolved_target}.'})}\n\n"

                # Step 2: Compute Stylometrics
                yield f"data: {json.dumps({'step': 2, 'name': 'stylometrics', 'status': 'running', 'message': 'Calculating stylometric typing patterns (emoji, casing, latency, slang)...'})}\n\n"
                stats = compute_stats(df_anon, media_count=media_counts.get(resolved_target, 0))
                yield f"data: {json.dumps({'step': 2, 'name': 'stylometrics', 'status': 'completed', 'message': 'Stylometric analysis complete.'})}\n\n"

                # Step 3: LLM Extraction
                model_name = llm_config.get("model", "")
                yield f"data: {json.dumps({'step': 3, 'name': 'llm_extraction', 'status': 'running', 'message': f'Extracting psychological profile & Big Five traits with {model_name}...'})}\n\n"
                dialogue, n_sess = sample_dialogue(df_anon, max_chars=50000)
                profile = extract_profile(dialogue, stats, llm_config)
                yield f"data: {json.dumps({'step': 3, 'name': 'llm_extraction', 'status': 'completed', 'message': f'Extracted Big Five scores and behavioral patterns across {n_sess} dialogue sessions.'})}\n\n"

                # Step 4: Assemble Prompt & Character Card
                yield f"data: {json.dumps({'step': 4, 'name': 'assembling', 'status': 'running', 'message': 'Assembling system prompt and SillyTavern character card...'})}\n\n"
                examples = pick_examples(df_anon, n=12)
                system_prompt = build_system_prompt(profile, stats, examples)
                character_card = build_character_card(char_name, profile, stats, examples)

                result = {
                    "success": True,
                    "target_name": resolved_target,
                    "char_name": char_name,
                    "profile": profile,
                    "stats": stats,
                    "examples": examples,
                    "system_prompt": system_prompt,
                    "character_card": character_card,
                }
                CACHE["last_result"] = result

                yield f"data: {json.dumps({'step': 4, 'name': 'assembling', 'status': 'completed', 'message': 'Persona successfully generated!', 'result': result})}\n\n"
            except Exception as e:
                yield f"data: {json.dumps({'status': 'error', 'error': str(e)})}\n\n"

        return Response(event_stream(), mimetype="text/event-stream")

    @app.route("/api/chat", methods=["POST"])
    def api_chat():
        data = request.get_json() or {}
        message = data.get("message", "").strip()
        history = data.get("history", [])
        system_prompt = data.get("system_prompt", "")
        char_name = data.get("char_name", "Fossetta")
        user_name = data.get("user_name", "You")

        provider = data.get("provider", "openrouter")
        api_key = data.get("api_key") or os.environ.get("OPENROUTER_API_KEY", "")
        model = data.get("model", "deepseek/deepseek-v4.1-flash")
        base_url = data.get("base_url")

        if not message:
            return jsonify({"success": False, "error": "Message cannot be empty."}), 400
        if not system_prompt:
            return jsonify({"success": False, "error": "System prompt is missing. Please generate a persona first."}), 400

        # Build message history for LLM
        prepared_system = system_prompt.replace("{{char}}", char_name).replace("{{user}}", user_name)
        llm_messages = [{"role": "system", "content": prepared_system}]

        for h in history:
            role = "assistant" if h.get("sender") == "char" else "user"
            llm_messages.append({"role": role, "content": h.get("text", "")})

        llm_messages.append({"role": "user", "content": message})

        try:
            reply = call_llm(
                messages=llm_messages,
                api_key=api_key,
                model=model,
                provider=provider,
                base_url=base_url,
                temperature=0.8,
                max_tokens=600,
            )
            return jsonify({"success": True, "reply": reply})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/api/download/<file_type>")
    def api_download(file_type):
        result = CACHE.get("last_result")
        if not result:
            return jsonify({"error": "No generated persona found to download."}), 404

        char_name = result.get("char_name", "persona").lower().replace(" ", "_")

        if file_type == "system-prompt":
            buffer = io.BytesIO(result["system_prompt"].encode("utf-8"))
            return send_file(
                buffer,
                as_attachment=True,
                download_name=f"{char_name}_system_prompt.txt",
                mimetype="text/plain",
            )
        elif file_type == "character-card":
            buffer = io.BytesIO(json.dumps(result["character_card"], ensure_ascii=False, indent=2).encode("utf-8"))
            return send_file(
                buffer,
                as_attachment=True,
                download_name=f"{char_name}_character_card.json",
                mimetype="application/json",
            )
        elif file_type == "profile":
            buffer = io.BytesIO(json.dumps(result["profile"], ensure_ascii=False, indent=2).encode("utf-8"))
            return send_file(
                buffer,
                as_attachment=True,
                download_name=f"{char_name}_profile.json",
                mimetype="application/json",
            )
        elif file_type == "stylometry":
            buffer = io.BytesIO(json.dumps(result["stats"], ensure_ascii=False, indent=2).encode("utf-8"))
            return send_file(
                buffer,
                as_attachment=True,
                download_name=f"{char_name}_stylometry.json",
                mimetype="application/json",
            )
        else:
            return jsonify({"error": "Invalid file type requested."}), 400

    return app


app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)

from flask import Flask, request, jsonify
from ia_api import reconhecer_rosto

app = Flask(__name__)

@app.route("/reconhecer", methods=["POST"])
def reconhecer():
    data = request.json
    if not data or "imagem" not in data:
        return jsonify({"status": "erro", "mensagem": "Imagem não enviada"}), 400

    imagem = data["imagem"]
    resultado = reconhecer_rosto(imagem)
    return jsonify(resultado)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, threaded=True)

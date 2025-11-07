import os
import cv2
import base64
import numpy as np
from deepface import DeepFace

# Configurações
MODELO = "Facenet"
DETECTOR = "retinaface"
LIMITE_CONFIANCA = 0.5  # 50%
DIRETORIO_IMAGENS = "imagens_conhecidas"

_model = None

def carregar_modelo():
    global _model
    if _model is None:
        print("[IA] Carregando modelo...")
        _model = DeepFace.build_model(MODELO)
    return _model

def decode_base64_image(image_base64):
    try:
        img_bytes = base64.b64decode(image_base64)
        np_arr = np.frombuffer(img_bytes, np.uint8)
        img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        return img
    except Exception as e:
        return None

def reconhecer_rosto(image_base64):
    model = carregar_modelo()
    img = decode_base64_image(image_base64)

    if img is None:
        return {"status": "erro", "mensagem": "Falha ao decodificar imagem"}

    try:
        rostos = DeepFace.extract_faces(
            img_path=img,
            detector_backend=DETECTOR,
            enforce_detection=False
        )
    except Exception as e:
        return {"status": "erro", "mensagem": f"Falha ao detectar rosto: {str(e)}"}

    if not rostos:
        return {"status": "sucesso", "identidade": "Nenhum rosto detectado"}

    # Considerando apenas o primeiro rosto detectado
    rosto = rostos[0]
    if rosto["confidence"] < LIMITE_CONFIANCA:
        return {"status": "sucesso", "identidade": "Desconhecido"}

    facial_area = rosto["facial_area"]

    # Buscar candidatos no banco de imagens
    try:
        candidatos = DeepFace.find(
            img_path=img,
            db_path=DIRETORIO_IMAGENS,
            model_name=MODELO,
            detector_backend=DETECTOR,
            enforce_detection=False
        )
    except Exception as e:
        candidatos = []

    nome_final = "Desconhecido"
    distancia_final = None

    if candidatos and len(candidatos) > 0:
        pessoas = {}
        for _, row in candidatos[0].iterrows():
            pessoa = os.path.basename(os.path.dirname(row["identity"]))
            distancia = row["distance"]
            if pessoa not in pessoas or distancia < pessoas[pessoa]:
                pessoas[pessoa] = distancia

        if pessoas:
            pessoa_mais_proxima = min(pessoas, key=pessoas.get)
            distancia_final = pessoas[pessoa_mais_proxima]
            if distancia_final <= LIMITE_CONFIANCA:
                nome_final = pessoa_mais_proxima

    return {
        "status": "sucesso",
        "identidade": nome_final,
        "distancia": float(distancia_final) if distancia_final else None,
        "facial_area": {
            "x": facial_area["x"],
            "y": facial_area["y"],
            "w": facial_area["w"],
            "h": facial_area["h"]
        },
        "confiança": float(rosto["confidence"])
    }

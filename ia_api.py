import os
import cv2
import base64
import numpy as np
from deepface import DeepFace

# Configurações principais
MODELO = "Facenet"
DETECTOR = "retinaface"
LIMITE_CONFIANCA = 0.5  # 50%
DIRETORIO_IMAGENS = "imagens_conhecidas"

# Cache do modelo
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
        return cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
    except Exception:
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
        return {"status": "sucesso", "resultado": "Nenhum rosto detectado"}

    resultados = []
    for rosto in rostos:
        if rosto["confidence"] < LIMITE_CONFIANCA:
            continue

        fa = rosto["facial_area"]  # Corrigido
        x, y, w, h = fa["x"], fa["y"], fa["w"], fa["h"]

        if w < 40 or h < 40:
            continue

        try:
            candidatos = DeepFace.find(
                img_path=img,
                db_path=DIRETORIO_IMAGENS,
                model_name=MODELO,
                detector_backend=DETECTOR,
                enforce_detection=False
            )
        except Exception:
            candidatos = []

        nome_final = "Desconhecido"
        distancia_final = None

        if candidatos:
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

        resultados.append({
            "nome": nome_final,
            "distancia": float(distancia_final) if distancia_final else None,
            "confianca": float(rosto["confidence"]),
            "area": fa
        })

    if not resultados:
        return {"status": "sucesso", "resultado": "Nenhum rosto válido"}

    return {"status": "sucesso", "resultado": resultados}

from flask import Flask, request, jsonify
from deepface import DeepFace
import numpy as np
import base64
import cv2
import os
import time
import logging

app = Flask(__name__)

# --- CONFIGURAÇÕES CENTRALIZADAS ---
MODELO_RECONHECIMENTO = "Facenet"
METRICA_DISTANCIA = "euclidean_l2"
DETECTOR_ROSTO = "retinaface"
LIMITE_CONFIANCA = 0.65   # ajuste se quiser ser mais/menos rigoroso
BANCO_DE_DADOS = "imagens_conhecidas"
MIN_FACE_WIDTH = 40       # px mínimo aceitável para considerar que há um rosto (ajuste conforme sua câmera)
MIN_FACE_HEIGHT = 40
TOP_K = 5                 # quantas "melhores pessoas" retornar no debug
# ---------------------------------------------------

# Pré-carregamento do modelo de reconhecimento (não tente build_model com detector backend)
print("="*40)
print("INICIANDO SERVIDOR E CARREGANDO MODELOS DE IA...")
try:
    _ = DeepFace.build_model(MODELO_RECONHECIMENTO)
    print(f"Modelo de reconhecimento '{MODELO_RECONHECIMENTO}' carregado!")
except Exception as e:
    logging.error(f"Erro crítico ao carregar modelo de reconhecimento: {e}")
print("Servidor pronto para receber requisições.")
print("="*40)
# ---------------------------------------------------

def safe_basename_parent(path):
    """Retorna o nome da pasta pai (p.ex. imagens_conhecidas/Nome/img.jpg -> Nome)."""
    try:
        return os.path.basename(os.path.dirname(path))
    except Exception:
        return path

@app.route('/reconhecer', methods=['POST'])
def reconhecer_rosto_api():
    try:
        dados_recebidos = request.get_json()
        if not dados_recebidos or 'imagem' not in dados_recebidos:
            return jsonify({'status': 'erro', 'mensagem': 'Nenhuma imagem enviada'}), 400

        # decodifica imagem
        imagem_base64 = dados_recebidos['imagem']
        imagem_bytes = base64.b64decode(imagem_base64)
        imagem_np = np.frombuffer(imagem_bytes, np.uint8)
        frame = cv2.imdecode(imagem_np, cv2.IMREAD_COLOR)

        if frame is None:
            return jsonify({'status': 'erro', 'mensagem': 'Imagem inválida'}), 400

        # extração de faces (já recorta e alinha conforme backend)
        rostos_extraidos = DeepFace.extract_faces(
            img_path=frame,
            detector_backend=DETECTOR_ROSTO,
            enforce_detection=False
        )

        # não encontrou rosto
        if not rostos_extraidos or len(rostos_extraidos) == 0 or rostos_extraidos[0].get('confidence', 0) == 0:
            return jsonify({
                'status': 'sucesso',
                'identidade': 'Nenhum rosto detectado',
                'distancia': None,
                'top_matches': []
            })

        # valida tamanho do rosto detectado (evita comparações com mini-faces ou falsas detecções)
        facial_area = rostos_extraidos[0].get('facial_area', {})
        w = facial_area.get('w', 0)
        h = facial_area.get('h', 0)
        if w < MIN_FACE_WIDTH or h < MIN_FACE_HEIGHT:
            return jsonify({
                'status': 'sucesso',
                'identidade': 'Nenhum rosto detectado',
                'distancia': None,
                'top_matches': []
            })

        rosto_alinhado = rostos_extraidos[0]['face']  # numpy array do rosto recortado/alinhado

        # comparações no banco
        resultados = DeepFace.find(
            img_path=rosto_alinhado,
            db_path=BANCO_DE_DADOS,
            model_name=MODELO_RECONHECIMENTO,
            distance_metric=METRICA_DISTANCIA,
            enforce_detection=False
        )

        # resultados é lista; pegamos o primeiro DataFrame
        if not resultados or resultados[0].empty:
            return jsonify({
                'status': 'sucesso',
                'identidade': 'Desconhecido',
                'distancia': None,
                'top_matches': []
            })

        df = resultados[0].copy()

        # DEBUG seguro (evita dependência tabulate)
        try:
            print("\n--- DEBUG DO SERVIDOR (head) ---")
            print(df.head(10).to_string(index=False))
            print("-------------------------------\n")
        except Exception:
            pass

        # Normalização: extrai nome da pessoa (pasta)
        df['person'] = df['identity'].apply(lambda p: safe_basename_parent(p))

        # Agrupa por pessoa e pega a menor distância (min distance) — evita bias por quem tem mais imagens
        grouped = df.groupby('person', as_index=False)['distance'].min()
        grouped_sorted = grouped.sort_values('distance', ascending=True).reset_index(drop=True)

        # prepara top matches para debug/cliente
        top_matches = grouped_sorted.head(TOP_K).to_dict(orient='records')

        # pega o melhor
        best = grouped_sorted.iloc[0]
        best_person = best['person']
        best_distance = float(best['distance'])

        # decisão com threshold
        if best_distance <= LIMITE_CONFIANCA:
            resposta = {
                'status': 'sucesso',
                'identidade': best_person,
                'distancia': best_distance,
                'top_matches': top_matches,
                'facial_area': facial_area
            }
        else:
            resposta = {
                'status': 'sucesso',
                'identidade': 'Desconhecido',
                'distancia': best_distance,
                'top_matches': top_matches,
                'facial_area': facial_area
            }

        print(f"Enviando resposta final: {resposta}")
        return jsonify(resposta)

    except Exception as e:
        logging.exception("Ocorreu um erro na rota /reconhecer")
        return jsonify({'status': 'erro', 'mensagem': str(e)}), 500


@app.route('/adicionar_rosto', methods=['POST'])
def adicionar_rosto():
    try:
        dados = request.get_json()
        imagem_base64 = dados.get('imagem')
        nome_da_pessoa = dados.get('nome', '').replace(" ", "_").strip()

        if not imagem_base64 or not nome_da_pessoa:
            return jsonify({'status': 'erro', 'mensagem': 'Imagem e nome são obrigatórios'}), 400

        imagem_bytes = base64.b64decode(imagem_base64)
        caminho_pasta = os.path.join(BANCO_DE_DADOS, nome_da_pessoa)
        os.makedirs(caminho_pasta, exist_ok=True)

        timestamp = int(time.time())
        caminho_foto = os.path.join(caminho_pasta, f"{nome_da_pessoa}_{timestamp}.jpg")

        with open(caminho_foto, "wb") as f:
            f.write(imagem_bytes)

        # Remove cache para forçar recálculo (representations)
        cache_file = os.path.join(BANCO_DE_DADOS, "representations_facenet.pkl")
        if os.path.exists(cache_file):
            try:
                os.remove(cache_file)
                print(f"Cache '{cache_file}' removido.")
            except Exception as e:
                print(f"Falha ao remover cache: {e}")

        return jsonify({'status': 'sucesso', 'mensagem': f'Rosto de {nome_da_pessoa} adicionado com sucesso!'})

    except Exception as e:
        logging.exception("Ocorreu um erro na rota /adicionar_rosto")
        return jsonify({'status': 'erro', 'mensagem': str(e)}), 500


if __name__ == '__main__':
    # threaded=True ok para dev; em produção use WSGI server
    app.run(host='0.0.0.0', port=5000, threaded=True)

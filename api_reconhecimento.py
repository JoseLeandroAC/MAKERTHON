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
METRICA_DISTANCIA = "cosine"  # Mudança para métrica mais confiável
DETECTOR_ROSTO = "retinaface"
LIMITE_CONFIANCA = 0.4  # Ajustável conforme testes
BANCO_DE_DADOS = "imagens_conhecidas"
# ---------------------------------------------------

# --- PRÉ-CARREGAMENTO DOS MODELOS DE IA ---
print("="*40)
print("INICIANDO SERVIDOR E CARREGANDO MODELOS DE IA...")
try:
    modelo_facenet = DeepFace.build_model(MODELO_RECONHECIMENTO)
    print(f"Modelo de reconhecimento '{MODELO_RECONHECIMENTO}' carregado!")
except Exception as e:
    logging.error(f"Erro crítico ao carregar modelo de reconhecimento: {e}")
print("Servidor pronto para receber requisições.")
print("="*40)
# ---------------------------------------------------

@app.route('/reconhecer', methods=['POST'])
def reconhecer_rosto_api():
    try:
        dados_recebidos = request.get_json()
        if 'imagem' not in dados_recebidos:
            return jsonify({'status': 'erro', 'mensagem': 'Nenhuma imagem enviada'}), 400

        # Decodifica imagem enviada
        imagem_base64 = dados_recebidos['imagem']
        imagem_bytes = base64.b64decode(imagem_base64)
        imagem_np = np.frombuffer(imagem_bytes, np.uint8)
        frame = cv2.imdecode(imagem_np, cv2.IMREAD_COLOR)

        # Detecta e alinha rostos
        rostos_extraidos = DeepFace.extract_faces(
            img_path=frame,
            detector_backend=DETECTOR_ROSTO,
            enforce_detection=True  # força pegar o rosto correto
        )

        if not rostos_extraidos or rostos_extraidos[0]['confidence'] == 0:
            return jsonify({
                'status': 'sucesso',
                'identidade': 'Nenhum rosto detectado',
                'distancia': None
            })

        # Pega primeiro rosto detectado
        rosto_alinhado = rostos_extraidos[0]['face']

        # DEBUG: mostra o rosto detectado
        cv2.imshow("Rosto detectado", rosto_alinhado)
        cv2.waitKey(1)  # mantém a janela aberta por 1ms

        # Compara com o banco de dados
        resultados_df = DeepFace.find(
            img_path=rosto_alinhado,
            db_path=BANCO_DE_DADOS,
            model_name=MODELO_RECONHECIMENTO,
            distance_metric=METRICA_DISTANCIA,
            enforce_detection=False
        )

        # DEBUG: imprime DataFrame retornado
        print("\n--- DEBUG DO SERVIDOR ---")
        if not resultados_df or resultados_df[0].empty:
            print("DeepFace não encontrou correspondências no banco de dados.")
        else:
            print(resultados_df[0].to_markdown(index=False))
        print("-------------------------\n")

        # Define resposta
        if resultados_df and not resultados_df[0].empty:
            distancia = resultados_df[0]['distance'][0]
            if distancia <= LIMITE_CONFIANCA:
                caminho_identidade = resultados_df[0]['identity'][0]
                nome_pessoa = os.path.basename(os.path.dirname(caminho_identidade))
                resposta = {
                    'status': 'sucesso',
                    'identidade': nome_pessoa,
                    'distancia': float(distancia)
                }
            else:
                resposta = {
                    'status': 'sucesso',
                    'identidade': 'Desconhecido',
                    'distancia': float(distancia)
                }
        else:
            resposta = {
                'status': 'sucesso',
                'identidade': 'Desconhecido',
                'distancia': None
            }

        print(f"Enviando resposta final: {resposta}")
        return jsonify(resposta)

    except Exception as e:
        logging.exception("Erro na rota /reconhecer")
        return jsonify({'status': 'erro', 'mensagem': str(e)}), 500


@app.route('/adicionar_rosto', methods=['POST'])
def adicionar_rosto():
    try:
        dados = request.get_json()
        imagem_base64 = dados['imagem']
        nome_da_pessoa = dados['nome'].replace(" ", "_").strip()

        if not nome_da_pessoa:
            return jsonify({'status': 'erro', 'mensagem': 'Nome da pessoa não pode ser vazio'}), 400

        imagem_bytes = base64.b64decode(imagem_base64)
        caminho_pasta = os.path.join(BANCO_DE_DADOS, nome_da_pessoa)
        os.makedirs(caminho_pasta, exist_ok=True)

        timestamp = int(time.time())
        caminho_foto = os.path.join(caminho_pasta, f"{nome_da_pessoa}_{timestamp}.jpg")

        with open(caminho_foto, "wb") as f:
            f.write(imagem_bytes)

        # Remove cache para recálculo de embeddings
        cache_file = os.path.join(BANCO_DE_DADOS, "representations_facenet.pkl")
        if os.path.exists(cache_file):
            os.remove(cache_file)
            print(f"Cache '{cache_file}' removido.")

        return jsonify({'status': 'sucesso', 'mensagem': f'Rosto de {nome_da_pessoa} adicionado com sucesso!'})

    except Exception as e:
        logging.exception("Erro na rota /adicionar_rosto")
        return jsonify({'status': 'erro', 'mensagem': str(e)}), 500


if __name__ == '__main__':
    # threaded=True ajuda em múltiplas requisições
    app.run(host='0.0.0.0', port=5000, threaded=True)
